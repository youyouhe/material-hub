"""
Bid document deconstruction module.

Takes a bid (投标) Word document and deconstructs it into reusable material
units via the extractor's atomic/composite/text split:

  - atomic materials (single licenses, ID cards): per-image child doc + full OCR
  - composite docs (audit reports, contracts):    N images merged into one doc,
                                                  only leading pages OCR'd
  - text sections (technical narrative):          standalone text child doc

Each child becomes a DmsDocument linked back to the parent via meta_json.
Parent doc records child_doc_ids for reverse lookup.
"""

import io
import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from extractor import extract_materials, ExtractedMaterial, COMPOSITE_OCR_SAMPLE_PAGES

logger = logging.getLogger("materialhub.bid_deconstruct")

# Title keywords that indicate a document is a bid (投标书) worth deconstructing.
# Used by the trigger detection in dms_processor.
BID_TITLE_KEYWORDS = ("投标", "磋商", "响应文件", "招标", "标书", "应答文件")


def is_bid_document(title: str) -> bool:
    """Heuristic: does this document title look like a bid package?"""
    if not title:
        return False
    return any(kw in title for kw in BID_TITLE_KEYWORDS)


def deconstruct_bid_doc(parent_doc_id: int) -> dict:
    """Deconstruct a bid Word document into child material documents.

    Args:
        parent_doc_id: the DmsDocument id of the uploaded bid Word file.

    Returns:
        {"total": N, "child_doc_ids": [...], "atomic": a, "composite": c, "text": t}
    """
    from dms_models import (
        get_dms_session, DmsDocument, Revision, DmsFile, Folder,
    )

    DATA_DIR = os.getenv("DATA_DIR", "data")

    # 1. Resolve parent doc + its Word file path
    with get_dms_session() as session:
        parent = session.query(DmsDocument).filter(DmsDocument.id == parent_doc_id).first()
        if not parent:
            raise ValueError(f"Parent doc {parent_doc_id} not found")
        parent_title = parent.title
        cur_rev = parent.current_revision()
        if not cur_rev or not cur_rev.files:
            raise ValueError(f"Parent doc {parent_doc_id} has no file")
        dms_file = cur_rev.files[0]
        file_path = (
            os.path.join(DATA_DIR, dms_file.storage_path)
            if not os.path.isabs(dms_file.storage_path)
            else dms_file.storage_path
        )

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Word file not found: {file_path}")

    logger.info("Deconstructing bid doc %d: %s", parent_doc_id, parent_title)

    # 2. Extract materials (in-memory, no disk writes)
    materials = extract_materials(file_path, output_dir=None)
    if not materials:
        logger.warning("No materials extracted from doc %d", parent_doc_id)
        return {"total": 0, "child_doc_ids": [], "atomic": 0, "composite": 0, "text": 0}

    # 3. Create child documents for each material
    child_ids = []
    counts = {"atomic": 0, "composite": 0, "text": 0}

    for mat in materials:
        try:
            child_id = _create_child_document(parent_doc_id, parent_title, mat, DATA_DIR)
            if child_id:
                child_ids.append(child_id)
                counts[mat.nature] += 1
        except Exception as e:
            logger.warning(
                "Failed to create child for '%s' (nature=%s): %s",
                mat.title, mat.nature, e,
            )

    # 4. Process each child (OCR / LLM classify) in background-friendly fashion
    #    We do it inline here since the parent pipeline already runs in a thread.
    for child_id in child_ids:
        try:
            _process_child(child_id)
        except Exception as e:
            logger.warning("Child %d processing failed (non-fatal): %s", child_id, e)

    # 5. Link parent → children via meta_json
    with get_dms_session() as session:
        parent = session.query(DmsDocument).filter(DmsDocument.id == parent_doc_id).first()
        if parent:
            meta = json.loads(parent.meta_json) if isinstance(parent.meta_json, str) else (parent.meta_json or {})
            if not isinstance(meta, dict):
                meta = {}
            meta["_bid_deconstruction"] = {
                "child_doc_ids": child_ids,
                "total_extracted": len(child_ids),
                "counts": counts,
                "deconstructed_at": datetime.utcnow().isoformat(),
            }
            parent.meta_json = json.dumps(meta, ensure_ascii=False)

    result = {"total": len(child_ids), "child_doc_ids": child_ids, **counts}
    logger.info(
        "Deconstruction of doc %d complete: %d children (atomic=%d, composite=%d, text=%d)",
        parent_doc_id, len(child_ids), counts["atomic"], counts["composite"], counts["text"],
    )
    return result


def _create_child_document(
    parent_doc_id: int, parent_title: str, mat: ExtractedMaterial, data_dir: str
) -> Optional[int]:
    """Create a child DmsDocument + Revision + Files for one extracted material."""
    from dms_models import get_dms_session, DmsDocument, Revision, DmsFile

    # Build child title: "parent_title - section title"
    child_title = mat.title or "未命名材料"

    meta = {
        "_bid_parent": {
            "parent_doc_id": parent_doc_id,
            "parent_title": parent_title,
            "source_section": mat.section,
            "source_title": mat.title,
        },
        "_material_nature": mat.nature,
        "_processing": {"status": "pending"},
    }
    if mat.expiry_date:
        meta["_detected_expiry"] = mat.expiry_date
    if mat.nature == "composite" and mat.images:
        meta["_composite_meta"] = {"page_count": len(mat.images)}

    with get_dms_session() as session:
        doc = DmsDocument(
            title=child_title,
            status="draft",
            meta_json=json.dumps(meta, ensure_ascii=False),
        )
        session.add(doc)
        session.flush()

        rev = Revision(document_id=doc.id, version_number=1, is_current=True)
        session.add(rev)
        session.flush()

        # Persist images as DmsFiles under dms_files/{child_doc}/{rev}/
        rev_dir = os.path.join(data_dir, "dms_files", str(doc.id), str(rev.id))
        os.makedirs(rev_dir, exist_ok=True)

        for img in mat.images:
            safe_fname = img.filename or f"image_{doc.id}_{img.ext}.{img.ext}"
            storage_path = f"dms_files/{doc.id}/{rev.id}/{safe_fname}"
            full_path = os.path.join(data_dir, storage_path)
            with open(full_path, "wb") as f:
                f.write(img.data)

            mime = f"image/{img.ext}" if img.ext != "jpg" else "image/jpeg"
            dms_file = DmsFile(
                revision_id=rev.id,
                file_type="original",
                filename=safe_fname,
                storage_path=storage_path,
                mime_type=mime,
                file_size=len(img.data),
            )
            session.add(dms_file)

        # For text-only materials, store the text in meta for KB chunking
        if mat.nature == "text" and mat.text:
            meta["_extracted_text"] = mat.text[:50000]
            doc.meta_json = json.dumps(meta, ensure_ascii=False)

        session.commit()
        logger.info("Created child doc %d: '%s' (%s, %d images)",
                    doc.id, child_title, mat.nature, len(mat.images))
        return doc.id


def _process_child(child_doc_id: int) -> None:
    """Process a child document according to its nature.

    - atomic:    full OCR each image → LLM classify → entity link → folder
    - composite: OCR only leading pages → light LLM metadata → no deep extraction
    - text:      LLM classify on stored text → entity link → folder
    """
    from dms_models import get_dms_session, DmsDocument
    from dms_processor import (
        _auto_assign_doc_type, _auto_assign_folder,
        _link_entities, _set_expiry_date, _update_processing,
    )
    from ocr_client import ocr_image_bytes

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == child_doc_id).first()
        if not doc:
            return
        meta = json.loads(doc.meta_json) if isinstance(doc.meta_json, str) else (doc.meta_json or {})
        nature = meta.get("_material_nature", "atomic")
        doc_title = doc.title or ""
        rev = doc.current_revision()
        if not rev:
            return
        # Extract file paths INSIDE the session (avoid detached-instance errors)
        file_paths = [
            (f.storage_path, f.filename)
            for f in rev.files if f.file_type == "original"
        ]

    _update_processing(child_doc_id, "processing")

    try:
        # Note: text sections are no longer extracted by the extractor (they are
        # project-specific, not reusable). Only atomic/composite reach here.
        if nature == "atomic":
            # Atomic: OCR every image fully, concatenate
            all_text = []
            for storage_path, filename in file_paths:
                full_path = os.path.join(os.getenv("DATA_DIR", "data"), storage_path)
                if os.path.exists(full_path):
                    with open(full_path, "rb") as fh:
                        ocr_text = ocr_image_bytes(fh.read(), label=filename)
                    if ocr_text:
                        all_text.append(ocr_text)
            combined = "\n\n".join(all_text)
            if combined:
                _classify_and_link(child_doc_id, combined[:4000], doc_title)

        elif nature == "composite":
            # Composite: OCR only leading pages for metadata
            sample_text = []
            for storage_path, filename in file_paths[:COMPOSITE_OCR_SAMPLE_PAGES]:
                full_path = os.path.join(os.getenv("DATA_DIR", "data"), storage_path)
                if os.path.exists(full_path):
                    with open(full_path, "rb") as fh:
                        ocr_text = ocr_image_bytes(fh.read(), label=filename)
                    if ocr_text:
                        sample_text.append(ocr_text)
            combined = "\n\n".join(sample_text)
            if combined:
                # Light classification — extract type/period/issuer only
                _classify_and_link(child_doc_id, combined[:3000], doc_title, light=True)

        _update_processing(child_doc_id, "completed")
        # Activate the child document
        with get_dms_session() as session:
            d = session.query(DmsDocument).filter(DmsDocument.id == child_doc_id).first()
            if d and d.status == "draft":
                d.status = "active"

    except Exception as e:
        logger.warning("Child %d processing error: %s", child_doc_id, e)
        _update_processing(child_doc_id, "failed", error=str(e))


def _classify_and_link(
    doc_id: int, text: str, title: str, light: bool = False
) -> None:
    """Run LLM classification on extracted text, then entity-link + folder-route.

    Args:
        light: if True, only extract high-level metadata (for composite docs).
    """
    from ocr_agent import intelligent_extract
    from dms_processor import (
        _auto_assign_doc_type, _auto_assign_folder,
        _link_entities, _set_expiry_date,
    )

    result = intelligent_extract(text, material_title=title)
    material_type = result.get("material_type", "")
    extracted_data = result.get("extracted_data", {})

    if material_type:
        _auto_assign_doc_type(doc_id, material_type)
        _auto_assign_folder(doc_id)
        if not light:
            _link_entities(doc_id, material_type, extracted_data)
            _set_expiry_date(doc_id, extracted_data)

    logger.info(
        "Classified doc %d: type=%s (light=%s)", doc_id, material_type, light
    )

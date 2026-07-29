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


def _llm_judge_composite(sample_texts: list[str], title: str) -> dict:
    """Ask LLM whether the sampled images are pages of one document or independent materials.

    Returns: {"is_single_document": bool, "reason": str}
    """
    from llm_provider import get_llm_provider

    # Truncate each sample to keep prompt short
    excerpts = []
    for i, text in enumerate(sample_texts, 1):
        excerpts.append(f"--- 图{i} OCR摘录 ---\n{text[:500]}")
    combined_excerpts = "\n\n".join(excerpts)

    prompt = f"""判断以下来自投标文件"{title}"章节的多张图片扫描件，是【同一份文档的多个页面】，还是【多份独立的证件/证明材料】。

{combined_excerpts}

判断依据：
- 如果是同一份文档的多页（如审计报告第1-30页、合同正文的连续页），返回 is_single_document=true
- 如果是多份独立的证件或证明（如不同人的社保证明、多张不同的资格证书），返回 is_single_document=false

只返回JSON，不要解释：
{{"is_single_document": true/false, "reason": "一句话理由"}}"""

    try:
        provider = get_llm_provider()
        result = provider.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0,
        )
        import re
        m = re.search(r'\{[^}]+\}', result)
        if m:
            return json.loads(m.group())
    except Exception as e:
        logger.warning("LLM composite judge failed: %s", e)

    # Default: assume single document (safe — don't split)
    return {"is_single_document": True, "reason": "LLM判断失败，默认保持合并"}

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
    - composite: OCR leading pages → LLM judges if one doc or independent →
                 either classify as-is or split into atomic children
    """
    from dms_models import get_dms_session, DmsDocument
    from dms_processor import _update_processing
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
        file_paths = [
            (f.storage_path, f.filename)
            for f in rev.files if f.file_type == "original"
        ]

    _update_processing(child_doc_id, "processing")

    try:
        if nature == "atomic":
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
            # OCR leading pages, then LLM decides: one document or independent?
            sample_texts = []
            for storage_path, filename in file_paths[:COMPOSITE_OCR_SAMPLE_PAGES]:
                full_path = os.path.join(os.getenv("DATA_DIR", "data"), storage_path)
                if os.path.exists(full_path):
                    with open(full_path, "rb") as fh:
                        ocr_text = ocr_image_bytes(fh.read(), label=filename)
                    if ocr_text:
                        sample_texts.append(ocr_text)

            if not sample_texts:
                logger.warning("Composite doc %d: no OCR text from samples", child_doc_id)
            else:
                judgment = _llm_judge_composite(sample_texts, doc_title)
                logger.info("Composite doc %d LLM judgment: %s", child_doc_id, judgment)

                if judgment.get("is_single_document", True):
                    combined = "\n\n".join(sample_texts)
                    _classify_and_link(child_doc_id, combined[:3000], doc_title, light=True)
                else:
                    logger.info("Composite doc %d: splitting into independent materials", child_doc_id)
                    _split_composite_to_atomic(child_doc_id, file_paths, doc_title)

        _update_processing(child_doc_id, "completed")
        with get_dms_session() as session:
            d = session.query(DmsDocument).filter(DmsDocument.id == child_doc_id).first()
            if d and d.status == "draft":
                d.status = "active"

    except Exception as e:
        logger.warning("Child %d processing error: %s", child_doc_id, e)
        _update_processing(child_doc_id, "failed", error=str(e))


def _split_composite_to_atomic(parent_doc_id: int, file_paths: list, doc_title: str) -> None:
    """Split a composite doc (misjudged as one doc but actually independent materials).

    Each image becomes its own atomic child doc with full OCR + classification.
    The original composite doc is marked as 'archived' (kept as record, not deleted).
    """
    from dms_models import get_dms_session, DmsDocument, Revision, DmsFile
    from ocr_client import ocr_image_bytes

    split_ids = []
    for storage_path, filename in file_paths:
        try:
            full_path = os.path.join(os.getenv("DATA_DIR", "data"), storage_path)
            if not os.path.exists(full_path):
                continue
            # OCR this image
            with open(full_path, "rb") as fh:
                ocr_text = ocr_image_bytes(fh.read(), label=filename)
            if not ocr_text:
                continue

            # Create a new atomic doc for this image
            meta = {
                "_bid_parent": {"parent_doc_id": parent_doc_id, "source_title": doc_title},
                "_material_nature": "atomic",
                "_split_from_composite": parent_doc_id,
                "_processing": {"status": "split"},
            }
            with get_dms_session() as session:
                child = DmsDocument(
                    title=f"{doc_title} - {filename}",
                    status="draft",
                    meta_json=json.dumps(meta, ensure_ascii=False),
                )
                session.add(child)
                session.flush()

                rev = Revision(document_id=child.id, version_number=1, is_current=True)
                session.add(rev)
                session.flush()

                dms_file = DmsFile(
                    revision_id=rev.id,
                    file_type="original",
                    filename=filename,
                    storage_path=storage_path,
                    mime_type="image/png",
                    file_size=os.path.getsize(full_path),
                )
                session.add(dms_file)
                session.commit()
                split_ids.append(child.id)

            # Classify the split child
            _classify_and_link(child.id, ocr_text[:4000], doc_title)
            with get_dms_session() as session:
                d = session.query(DmsDocument).filter(DmsDocument.id == child.id).first()
                if d and d.status == "draft":
                    d.status = "active"

        except Exception as e:
            logger.warning("Failed to split image %s from composite %d: %s", filename, parent_doc_id, e)

    # Archive the original composite (keep as record)
    if split_ids:
        with get_dms_session() as session:
            parent = session.query(DmsDocument).filter(DmsDocument.id == parent_doc_id).first()
            if parent:
                parent.status = "archived"
                meta = json.loads(parent.meta_json) if isinstance(parent.meta_json, str) else (parent.meta_json or {})
                meta["_split_into"] = split_ids
                parent.meta_json = json.dumps(meta, ensure_ascii=False)
        logger.info("Composite doc %d split into %d atomic docs: %s", parent_doc_id, len(split_ids), split_ids)


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

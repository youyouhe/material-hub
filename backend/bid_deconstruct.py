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


# Pages per LLM call when detecting document boundaries across a composite.
BOUNDARY_BATCH_PAGES = 8


def _llm_detect_boundaries(page_texts: list[str], title: str) -> list[dict]:
    """Detect document boundaries across consecutive scanned pages.

    Single-page materials (营业执照, 身份证, 授权书) must stay single;
    multi-page materials (审计报告, 合同, 财务报表附注) must stay merged.
    Returns [{"start": int(0-based), "doc_type": str, "doc_title": str}, ...] —
    each entry marks the first page of a new document; its pages run until the
    next entry. On total LLM failure returns a single boundary at page 0
    (keep everything merged — merging is always safer than over-splitting).
    """
    import re
    from llm_provider import get_llm_provider

    provider = get_llm_provider()
    n = len(page_texts)
    boundaries = []
    prev_doc_type = ""
    i = 0
    while i < n:
        batch = page_texts[i:i + BOUNDARY_BATCH_PAGES]
        excerpts = []
        for j, text in enumerate(batch):
            excerpts.append(f"--- 第{i + j + 1}页 ---\n{(text or '')[:300] or '(无文本)'}")
        combined_excerpts = "\n\n".join(excerpts)
        ctx = (
            f"上一批最后一页属于「{prev_doc_type}」，本批第{i + 1}页可能是它的续页。"
            if prev_doc_type else "第1页是整个扫描件的第一页。"
        )
        prompt = f"""以下来自投标文件"{title}"的连续扫描页 OCR 摘录。{ctx}
请判断本批每一页是【新文档的第一页】还是【前一份文档的续页】。

判断依据：
- 营业执照、身份证、授权书、承诺书、缴纳凭证等通常只有 1 页
- 审计报告、财务报表附注、合同等是连续多页的同一份文档（页码/页眉连续，如"第12页"）
- 出现新的封面或标题（如"2024年度审计报告"）= 新文档开始

只返回JSON数组，本批每页一项，不要解释：
[{{"page": 页码整数, "is_new_doc": true/false, "doc_type": "材料类型", "doc_title": "该页所属文档标题"}}]"""

        items = []
        # Up to 3 attempts per batch — an empty/timed-out response must not
        # silently turn the whole batch into "continuation" pages.
        for _attempt in range(3):
            try:
                result = provider.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=4000,
                    temperature=0,
                )
                m = re.search(r"\[.*\]", result or "", re.S)
                if m:
                    items = json.loads(m.group())
                if items:
                    break
                logger.warning("Boundary detection empty/unparsable for pages %d-%d (attempt %d)",
                               i + 1, i + len(batch), _attempt + 1)
            except Exception as e:
                logger.warning("Boundary detection failed for pages %d-%d (attempt %d): %s",
                               i + 1, i + len(batch), _attempt + 1, e)

        for j in range(len(batch)):
            page_no = i + j + 1
            item = None
            # LLMs often return batch-relative page numbers (1..k) despite
            # being shown absolute ones — accept both, prefer exact match.
            for x in items:
                if not isinstance(x, dict):
                    continue
                p = x.get("page")
                if p == page_no:
                    item = x
                    break
                if p == j + 1 or (isinstance(p, str) and p.isdigit() and int(p) == j + 1):
                    item = x  # relative match; keep scanning for exact
            if item:
                if item.get("is_new_doc"):
                    boundaries.append({
                        "start": page_no - 1,
                        "doc_type": item.get("doc_type", "") or "",
                        "doc_title": item.get("doc_title", "") or "",
                    })
                if item.get("doc_type"):
                    prev_doc_type = item["doc_type"]
        i += len(batch)

    if not boundaries or boundaries[0]["start"] != 0:
        boundaries.insert(0, {"start": 0, "doc_type": "", "doc_title": ""})
    return boundaries

from extractor import extract_materials, ExtractedMaterial

logger = logging.getLogger("materialhub.bid_deconstruct")

def deconstruct_bid_doc(parent_doc_id: int) -> dict:
    """Deconstruct a Word document into child material documents.

    Runs for any Word upload — no title heuristic. Documents without
    embedded materials extract to nothing and are left untouched.

    Args:
        parent_doc_id: the DmsDocument id of the uploaded Word file.

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
        # Idempotency: already deconstructed → return the recorded summary
        existing_meta = json.loads(parent.meta_json) if isinstance(parent.meta_json, str) else (parent.meta_json or {})
        if isinstance(existing_meta, dict):
            prev = existing_meta.get("_bid_deconstruction")
            if prev:
                logger.info("Doc %d already deconstructed (%d children), skipping",
                            parent_doc_id, prev.get("total_extracted", 0))
                return {
                    "total": prev.get("total_extracted", 0),
                    "child_doc_ids": prev.get("child_doc_ids", []),
                    **prev.get("counts", {}),
                }
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
            # OCR all pages + LLM boundary detection: single-page materials
            # stay single, multi-page documents stay merged.
            _split_composite_by_boundaries(child_doc_id, file_paths, doc_title)

        _update_processing(child_doc_id, "completed")
        with get_dms_session() as session:
            d = session.query(DmsDocument).filter(DmsDocument.id == child_doc_id).first()
            if d and d.status == "draft":
                d.status = "active"
        _index_child(child_doc_id)

    except Exception as e:
        logger.warning("Child %d processing error: %s", child_doc_id, e)
        _update_processing(child_doc_id, "failed", error=str(e))


def _split_composite_by_boundaries(child_doc_id: int, file_paths: list, doc_title: str) -> None:
    """Segment a composite's pages into whole documents via LLM boundary detection.

    Single-page materials (licenses, ID cards) become single-page child docs;
    multi-page documents (audit reports, contracts) become composite child docs
    carrying all their pages. If detection finds the whole composite is one
    document, it is classified as-is and kept. Otherwise the original composite
    is archived (kept as record, not deleted) after its groups are created.
    """
    from ocr_client import ocr_image_bytes

    # OCR every page (content-cached, so re-runs are cheap)
    page_texts = []
    for storage_path, filename in file_paths:
        full_path = os.path.join(os.getenv("DATA_DIR", "data"), storage_path)
        text = ""
        if os.path.exists(full_path):
            try:
                with open(full_path, "rb") as fh:
                    text = ocr_image_bytes(fh.read(), label=filename) or ""
            except Exception as e:
                logger.warning("OCR failed for %s of composite %d: %s", filename, child_doc_id, e)
        page_texts.append(text)

    if not any(page_texts):
        logger.warning("Composite doc %d: no OCR text on any page", child_doc_id)
        return

    boundaries = _llm_detect_boundaries(page_texts, doc_title)
    logger.info("Composite doc %d: %d document boundaries: %s",
                child_doc_id, len(boundaries), boundaries)

    n = len(file_paths)
    groups = []
    for k, b in enumerate(boundaries):
        end = boundaries[k + 1]["start"] if k + 1 < len(boundaries) else n
        if b["start"] < end:
            groups.append((b["start"], end, b.get("doc_type") or "", b.get("doc_title") or ""))

    # One group covering all pages → the composite IS one document, keep it
    if len(groups) <= 1:
        combined = "\n\n".join(t for t in page_texts if t)
        _classify_and_link(child_doc_id, combined[:4000], doc_title, light=True)
        return

    split_ids = []
    for start, end, doc_type, group_title in groups:
        try:
            gid = _create_group_document(
                child_doc_id, doc_title, group_title or doc_type,
                file_paths[start:end], page_texts[start:end],
            )
            if gid:
                split_ids.append(gid)
        except Exception as e:
            logger.warning("Failed to create group doc for pages %d-%d of composite %d: %s",
                           start + 1, end, child_doc_id, e)

    # Archive the original composite (keep as record)
    if split_ids:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as session:
            parent = session.query(DmsDocument).filter(DmsDocument.id == child_doc_id).first()
            if parent:
                parent.status = "archived"
                meta = json.loads(parent.meta_json) if isinstance(parent.meta_json, str) else (parent.meta_json or {})
                meta["_split_into"] = split_ids
                parent.meta_json = json.dumps(meta, ensure_ascii=False)
        logger.info("Composite doc %d split into %d documents: %s",
                    child_doc_id, len(split_ids), split_ids)


def _create_group_document(
    parent_doc_id: int, parent_title: str, group_title: str,
    group_files: list, group_texts: list,
) -> Optional[int]:
    """Create one child doc for a detected document (1+ consecutive pages).

    Files are referenced in place (same storage_path as the parent composite's
    revision files) — no bytes are copied.
    """
    from dms_models import get_dms_session, DmsDocument, Revision, DmsFile

    if not group_files:
        return None

    is_single = len(group_files) == 1
    title = f"{parent_title} - {group_title}" if group_title else parent_title
    meta = {
        "_bid_parent": {"parent_doc_id": parent_doc_id, "source_title": parent_title},
        "_material_nature": "atomic" if is_single else "composite",
        "_split_from_composite": parent_doc_id,
        "_processing": {"status": "split"},
    }
    with get_dms_session() as session:
        child = DmsDocument(
            title=title,
            status="draft",
            meta_json=json.dumps(meta, ensure_ascii=False),
        )
        session.add(child)
        session.flush()
        child_id = child.id

        rev = Revision(document_id=child_id, version_number=1, is_current=True)
        session.add(rev)
        session.flush()

        data_dir = os.getenv("DATA_DIR", "data")
        for storage_path, filename in group_files:
            full_path = os.path.join(data_dir, storage_path)
            if not os.path.exists(full_path):
                continue
            ext = os.path.splitext(filename)[1].lstrip(".").lower() or "png"
            dms_file = DmsFile(
                revision_id=rev.id,
                file_type="original",
                filename=filename,
                storage_path=storage_path,
                mime_type="image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}",
                file_size=os.path.getsize(full_path),
            )
            session.add(dms_file)
        session.commit()

    combined = "\n\n".join(t for t in group_texts if t)
    if combined:
        _classify_and_link(child_id, combined[:4000], title)
    with get_dms_session() as session:
        d = session.query(DmsDocument).filter(DmsDocument.id == child_id).first()
        if d and d.status == "draft":
            d.status = "active"
    _index_child(child_id)
    return child_id


def _index_child(doc_id: int) -> None:
    """FTS + KB indexing for a child doc (failures are non-fatal)."""
    try:
        from dms_search import index_document
        index_document(doc_id)
    except Exception as e:
        logger.warning("FTS indexing failed for child %d: %s", doc_id, e)
    try:
        from kb_ingest import ingest_document_chunks
        ingest_document_chunks(doc_id)
    except Exception as e:
        logger.warning("KB indexing failed for child %d: %s", doc_id, e)


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

    # Persist classification + searchable text into meta_json — FTS reads
    # summary/extracted_data, KB chunks read _analysis.combined_text
    from dms_models import get_dms_session, DmsDocument
    with get_dms_session() as session:
        d = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if d:
            meta = json.loads(d.meta_json) if isinstance(d.meta_json, str) else (d.meta_json or {})
            if not isinstance(meta, dict):
                meta = {}
            if material_type:
                meta["material_type"] = material_type
            if extracted_data:
                meta["extracted_data"] = extracted_data
            if result.get("summary"):
                meta["summary"] = result["summary"]
            if result.get("confidence") is not None:
                meta["confidence"] = result["confidence"]
            if text:
                analysis = meta.get("_analysis") or {}
                if isinstance(analysis, str):
                    try:
                        analysis = json.loads(analysis)
                    except (json.JSONDecodeError, TypeError):
                        analysis = {}
                analysis["combined_text"] = f"{d.title}\n\n{text}" if d.title else text
                meta["_analysis"] = analysis
            d.meta_json = json.dumps(meta, ensure_ascii=False)

    if material_type:
        _auto_assign_doc_type(doc_id, material_type)
        _auto_assign_folder(doc_id)
        if not light:
            _link_entities(doc_id, material_type, extracted_data)
            _set_expiry_date(doc_id, extracted_data)

    logger.info(
        "Classified doc %d: type=%s (light=%s)", doc_id, material_type, light
    )

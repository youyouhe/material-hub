"""
Document Pre-Analysis Module.

Analyzes uploaded documents before OCR to determine:
- Whether a PDF is text-based or scanned (image-only)
- Direct text extraction from text-based pages
- Per-page thumbnail generation
- Which pages likely need OCR (scanned/image pages)
"""

import gc

import hashlib
import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("materialhub.doc_analyzer")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DMS_FILES_DIR = DATA_DIR / "dms_files"

# Minimum characters per page to consider it "text-based"
TEXT_PAGE_THRESHOLD = 50


def _safe_remove_temp(path: str, retries: int = 3):
    """Remove a temp file with retries for Windows file-lock issues."""
    import time
    for i in range(retries):
        try:
            gc.collect()
            os.unlink(path)
            return
        except PermissionError:
            if i < retries - 1:
                time.sleep(0.5)
        except OSError:
            return


def analyze_document(doc_id: int) -> dict:
    """Pre-analyze a document: detect page types, extract text, generate thumbnails.

    Returns analysis result dict to be stored in meta_json._analysis:
    {
        "total_pages": int,
        "file_type": "pdf" | "image" | "word",
        "pages": [
            {
                "page_num": 0,          # 0-indexed
                "has_text": bool,       # True if extractable text found
                "text_length": int,
                "text": str | None,     # Extracted text (if text-based)
                "needs_ocr": bool,      # True if page is image-only
                "thumbnail_path": str,  # Storage path for thumbnail
            },
            ...
        ],
        "text_pages": [0, 2, 5],        # Pages with extractable text
        "ocr_pages": [1, 3, 4],         # Pages that need OCR
        "suggested_ocr_pages": [1, 3],  # Suggested subset for OCR
        "full_text": str | None,        # Combined text from text pages
    }
    """
    from dms_models import get_dms_session, DmsDocument, DmsFile

    # Get original file info
    file_info = _get_original_file(doc_id)
    if not file_info:
        return {"error": "No original file found"}

    file_path = str(DATA_DIR / file_info["storage_path"])
    mime_type = file_info["mime_type"]
    revision_id = file_info["revision_id"]

    if mime_type == "application/pdf":
        return _analyze_pdf(doc_id, file_path, revision_id)
    elif mime_type.startswith("image/"):
        return _analyze_image(doc_id, file_path, revision_id, mime_type)
    elif mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return {
            "total_pages": 1,
            "file_type": "word",
            "pages": [],
            "text_pages": [],
            "ocr_pages": [],
            "suggested_ocr_pages": [],
            "full_text": None,
        }
    else:
        return {"error": f"Unsupported mime type: {mime_type}"}


def _analyze_pdf(doc_id: int, file_path: str, revision_id: int) -> dict:
    """Analyze a PDF document page by page."""
    import fitz  # PyMuPDF

    pdf_doc = fitz.open(file_path)
    total_pages = len(pdf_doc)

    pages = []
    text_pages = []
    ocr_pages = []
    all_text_parts = []

    # Ensure thumbnail directory exists
    thumb_dir = DMS_FILES_DIR / str(doc_id) / str(revision_id) / "page_thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    for page_idx in range(total_pages):
        page = pdf_doc[page_idx]

        # Extract text
        text = page.get_text("text").strip()
        text_length = len(text)
        has_text = text_length >= TEXT_PAGE_THRESHOLD

        # Generate page thumbnail (200px width)
        zoom = 200.0 / page.rect.width if page.rect.width > 0 else 1.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        thumb_data = pix.tobytes("png")
        thumb_hash = hashlib.md5(thumb_data).hexdigest()[:8]
        thumb_filename = f"thumb_p{page_idx + 1}.png"
        thumb_storage = f"dms_files/{doc_id}/{revision_id}/page_thumbs/{thumb_hash}_{thumb_filename}"
        thumb_full_path = DATA_DIR / thumb_storage

        with open(thumb_full_path, "wb") as f:
            f.write(thumb_data)

        page_info = {
            "page_num": page_idx,
            "has_text": has_text,
            "text_length": text_length,
            "text": text if has_text else None,
            "needs_ocr": not has_text,
            "thumbnail_path": thumb_storage,
        }
        pages.append(page_info)

        if has_text:
            text_pages.append(page_idx)
            all_text_parts.append(text)
        else:
            ocr_pages.append(page_idx)

    pdf_doc.close()

    # Suggest OCR pages: all image-only pages, capped at 10 for large docs
    suggested_ocr = ocr_pages[:10] if len(ocr_pages) > 10 else list(ocr_pages)

    full_text = "\n\n".join(all_text_parts) if all_text_parts else None

    logger.info(
        f"PDF analysis for doc {doc_id}: {total_pages} pages, "
        f"{len(text_pages)} text, {len(ocr_pages)} need OCR"
    )

    return {
        "total_pages": total_pages,
        "file_type": "pdf",
        "pages": pages,
        "text_pages": text_pages,
        "ocr_pages": ocr_pages,
        "suggested_ocr_pages": suggested_ocr,
        "full_text": full_text,
    }


def _analyze_image(doc_id: int, file_path: str, revision_id: int, mime_type: str) -> dict:
    """Analyze a single image file."""
    from PIL import Image

    # Generate thumbnail
    thumb_dir = DMS_FILES_DIR / str(doc_id) / str(revision_id) / "page_thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(file_path)
        w, h = img.size
        new_w = 200
        new_h = int(h * (new_w / w)) if w > 0 else 200
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        img_resized.save(buf, format="PNG")
        thumb_data = buf.getvalue()
    except Exception as e:
        logger.warning(f"Failed to generate image thumbnail for doc {doc_id}: {e}")
        thumb_data = None

    thumb_storage = None
    if thumb_data:
        thumb_hash = hashlib.md5(thumb_data).hexdigest()[:8]
        thumb_storage = f"dms_files/{doc_id}/{revision_id}/page_thumbs/{thumb_hash}_thumb_p1.png"
        with open(DATA_DIR / thumb_storage, "wb") as f:
            f.write(thumb_data)

    return {
        "total_pages": 1,
        "file_type": "image",
        "pages": [{
            "page_num": 0,
            "has_text": False,
            "text_length": 0,
            "text": None,
            "needs_ocr": True,
            "thumbnail_path": thumb_storage,
        }],
        "text_pages": [],
        "ocr_pages": [0],
        "suggested_ocr_pages": [0],
        "full_text": None,
    }


def get_page_thumbnail(doc_id: int, page_num: int) -> Optional[str]:
    """Get the storage path for a page thumbnail. Returns None if not found."""
    from dms_models import get_dms_session, DmsDocument

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc or not doc.meta_json:
            return None

        try:
            meta = json.loads(doc.meta_json)
        except (json.JSONDecodeError, TypeError):
            return None

        analysis = meta.get("_analysis")
        if not analysis:
            return None

        pages = analysis.get("pages", [])
        for p in pages:
            if p["page_num"] == page_num:
                return p.get("thumbnail_path")

    return None


def run_selective_ocr(doc_id: int, page_numbers: list[int], ocr_provider_override: str = None) -> dict:
    """Run OCR on specific pages of a document.

    Args:
        doc_id: Document ID
        page_numbers: List of 0-indexed page numbers to OCR
        ocr_provider_override: Temporarily use a different OCR provider

    Returns:
        Dict mapping page_num -> ocr_text
    """
    from ocr_client import ocr_image, ocr_image_bytes, check_ocr_service, set_provider_override, clear_provider_override
    if ocr_provider_override:
        set_provider_override(ocr_provider_override)
    from ocr_cache import get_cached_ocr, save_ocr_to_cache

    file_info = _get_original_file(doc_id)
    if not file_info:
        return {}

    file_path = str(DATA_DIR / file_info["storage_path"])
    mime_type = file_info["mime_type"]

    if not check_ocr_service():
        if ocr_provider_override:
            clear_provider_override()
        raise RuntimeError("OCR service is not available")

    results = {}
    try:
        if mime_type.startswith("image/"):
            # Single image — only page 0 makes sense
            if 0 in page_numbers:
                # Skip cache when provider is overridden (re-OCR scenario)
                cached = None if ocr_provider_override else get_cached_ocr(file_path, 0)
                if cached:
                    results[0] = cached.get("text", "")
                else:
                    text = ocr_image(file_path, page_number=1)
                    if text:
                        save_ocr_to_cache(file_path, 0, text)
                        results[0] = text

        elif mime_type == "application/pdf":
            import fitz

            pdf_doc = fitz.open(file_path)
            total_pages = len(pdf_doc)

            for page_num in sorted(page_numbers):
                if page_num < 0 or page_num >= total_pages:
                    continue

                # Skip cache when provider is overridden (re-OCR scenario)
                cached = None if ocr_provider_override else get_cached_ocr(file_path, page_num)
                if cached:
                    results[page_num] = cached.get("text", "")
                    continue

                # Render page to PNG bytes in memory (no temp file needed)
                page = pdf_doc[page_num]
                pix = page.get_pixmap(dpi=200)
                png_bytes = pix.tobytes("png")

                text = ocr_image_bytes(png_bytes, page_number=page_num + 1, label=f"doc{doc_id}_p{page_num+1}")
                if text:
                    save_ocr_to_cache(file_path, page_num, text)
                    results[page_num] = text

            pdf_doc.close()
    finally:
        if ocr_provider_override:
            clear_provider_override()

    logger.info(f"Selective OCR for doc {doc_id}: requested {len(page_numbers)} pages, got {len(results)} results")
    return results


def _get_original_file(doc_id: int) -> Optional[dict]:
    """Get the original file info for a document."""
    from dms_models import get_dms_session, DmsDocument, DmsFile

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return None
        cur_rev = doc.current_revision()
        if not cur_rev:
            return None
        for f in cur_rev.files:
            if f.file_type == "original":
                return {
                    "id": f.id,
                    "revision_id": f.revision_id,
                    "storage_path": f.storage_path,
                    "mime_type": f.mime_type or "",
                    "filename": f.filename,
                }
    return None

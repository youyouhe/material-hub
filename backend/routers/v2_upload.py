"""DMS Upload and Review Queue API endpoints."""

import os
import json
import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Request
from pydantic import BaseModel

from dms_auth import require_role, get_current_user_id
from dms_audit import log_audit

from dms_models import (
    get_dms_session, DmsDocument, Revision, DmsFile,
    DocType, Folder, Entity, DocumentEntity,
    VALID_STATUS_TRANSITIONS,
)

logger = logging.getLogger("materialhub.routers.v2_upload")

router = APIRouter(prefix="/api/v2/upload", tags=["dms-upload"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DMS_FILES_DIR = DATA_DIR / "dms_files"
DMS_FILES_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    # Audio (ASR)
    "audio/mpeg", "audio/mp3", "audio/mpga", "audio/mpa",
    "audio/wav", "audio/wave", "audio/x-wav",
    "audio/ogg", "audio/flac", "audio/aac",
    "audio/webm", "audio/mp4", "audio/x-m4a",
    "application/octet-stream",  # Allow generic binary (ffmpeg handles conversion)
    # Video (extract audio → ASR)
    "video/mp4", "video/mpeg", "video/quicktime",
    "video/webm", "video/x-msvideo", "video/x-matroska",
    # Plain text
    "text/plain",
}


def _update_processing_status(doc_id: int, status: str, error: str = None):
    """Update the _processing key in document meta_json."""
    from datetime import datetime
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return
        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        processing = meta.get("_processing", {})
        processing["status"] = status
        if error:
            processing["error"] = error
        if status == "completed":
            processing["completed_at"] = datetime.utcnow().isoformat()
        meta["_processing"] = processing
        doc.meta_json = json.dumps(meta, ensure_ascii=False)


@router.post("/check-hash", dependencies=[require_role("editor")])
async def check_file_hash(file: UploadFile = File(...)):
    """Check if a file with the same hash already exists.

    Returns duplicate info if found, or empty result if no duplicate.
    """
    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()

    with get_dms_session() as session:
        existing = (
            session.query(DmsFile)
            .filter(DmsFile.file_hash == file_hash, DmsFile.file_type == "original")
            .first()
        )
        if existing:
            doc = existing.revision.document
            return {
                "duplicate": True,
                "file_hash": file_hash,
                "existing_document": {
                    "id": doc.id,
                    "title": doc.title,
                    "status": doc.status,
                    "folder": doc.folder.name if doc.folder else None,
                    "doc_type": doc.doc_type.name if doc.doc_type else None,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                },
            }

    return {"duplicate": False, "file_hash": file_hash}


@router.post("/", dependencies=[require_role("editor")])
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    folder_id: Optional[int] = Form(None),
    doc_type_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    force: Optional[bool] = Form(False),
):
    """Upload a file and create Document + Revision + File records.

    Triggers async background processing for OCR, classification, and entity linking.
    Set force=true to skip duplicate check.
    """
    # Validate MIME type (with extension-based override for audio)
    content_type = file.content_type or ""
    if content_type == "application/octet-stream":
        # Infer from file extension
        filename_lower = (file.filename or "").lower()
        ext_map = {
            ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
            ".flac": "audio/flac", ".aac": "audio/aac", ".m4a": "audio/x-m4a",
            ".webm": "audio/webm",
            ".mp4": "video/mp4", ".mkv": "video/x-matroska",
            ".avi": "video/x-msvideo", ".mov": "video/quicktime",
        }
        for ext, mime in ext_map.items():
            if filename_lower.endswith(ext):
                content_type = mime
                break
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. "
                   f"Allowed: PDF, JPEG, PNG, TIFF, DOCX, DOC, MP3, WAV, MP4",
        )

    # Read file content
    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()
    file_size = len(content)

    # Duplicate check (unless force=true)
    if not force:
        with get_dms_session() as session:
            existing = (
                session.query(DmsFile)
                .filter(DmsFile.file_hash == file_hash, DmsFile.file_type == "original")
                .first()
            )
            if existing:
                doc = existing.revision.document
                raise HTTPException(
                    status_code=409,
                    detail=json.dumps({
                        "code": "DUPLICATE_FILE",
                        "message": f"文件已存在: {doc.title}",
                        "existing_document": {
                            "id": doc.id,
                            "title": doc.title,
                            "status": doc.status,
                            "folder": doc.folder.name if doc.folder else None,
                            "doc_type": doc.doc_type.name if doc.doc_type else None,
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        },
                    }, ensure_ascii=False),
                )

    # Derive title from filename if not provided
    original_filename = file.filename or "untitled"
    if not title:
        title = Path(original_filename).stem

    # Validate optional foreign keys
    with get_dms_session() as session:
        if folder_id is not None:
            folder = session.query(Folder).filter(Folder.id == folder_id).first()
            if not folder:
                raise HTTPException(status_code=400, detail=f"Folder {folder_id} not found")

        if doc_type_id is not None:
            dt = session.query(DocType).filter(DocType.id == doc_type_id).first()
            if not dt:
                raise HTTPException(status_code=400, detail=f"DocType {doc_type_id} not found")

        # Create Document
        processing_meta = {"_processing": {"status": "pending"}}
        doc = DmsDocument(
            title=title,
            status="draft",
            folder_id=folder_id,
            doc_type_id=doc_type_id,
            description=notes,
            meta_json=json.dumps(processing_meta, ensure_ascii=False),
            created_by=get_current_user_id(request),
        )
        session.add(doc)
        session.flush()

        # Create Revision
        rev = Revision(
            document_id=doc.id,
            version_number=1,
            is_current=True,
        )
        session.add(rev)
        session.flush()

        # Store physical file
        rev_dir = DMS_FILES_DIR / str(doc.id) / str(rev.id)
        rev_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{file_hash[:8]}_{original_filename}"
        storage_path = f"dms_files/{doc.id}/{rev.id}/{safe_name}"
        full_path = DATA_DIR / storage_path

        with open(full_path, "wb") as f:
            f.write(content)

        # Create File record
        dms_file = DmsFile(
            revision_id=rev.id,
            file_type="original",
            filename=original_filename,
            storage_path=storage_path,
            mime_type=content_type,
            file_size=file_size,
            file_hash=file_hash,
        )
        session.add(dms_file)
        session.flush()

        doc_id = doc.id
        rev_id = rev.id

    logger.info(f"Upload created: doc={doc_id}, rev={rev_id}, file={original_filename} ({file_size} bytes)")

    # Kick off background pre-analysis (staged pipeline)
    from dms_processor import analyze_document
    thread = threading.Thread(
        target=analyze_document,
        args=(doc_id,),
        daemon=True,
    )
    thread.start()

    return {
        "document_id": doc_id,
        "revision_id": rev_id,
        "status": "processing",
    }


# ============================================================
# Processing Pipeline Endpoints (staged flow)
# ============================================================


@router.get("/process/{doc_id}", dependencies=[require_role("editor")])
async def get_processing_status(doc_id: int):
    """Get detailed processing status and analysis for a document."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        processing = meta.get("_processing", {})
        analysis = meta.get("_analysis", {})

        # Build page info for frontend (thumbnails as API URLs)
        pages = []
        for p in analysis.get("pages", []):
            pages.append({
                "page_num": p["page_num"],
                "has_text": p.get("has_text", False),
                "text_length": p.get("text_length", 0),
                "needs_ocr": p.get("needs_ocr", True),
                "ocr_text": p.get("ocr_text"),
                "thumbnail_url": f"/api/v2/upload/process/{doc_id}/page/{p['page_num']}/thumb"
                    if p.get("thumbnail_path") else None,
            })

        return {
            "document_id": doc_id,
            "title": doc.title,
            "status": doc.status,
            "processing_status": processing.get("status"),
            "processing_error": processing.get("error"),
            "total_pages": analysis.get("total_pages", 0),
            "file_type": analysis.get("file_type"),
            "pages": pages,
            "text_pages": analysis.get("text_pages", []),
            "ocr_pages": analysis.get("ocr_pages", []),
            "suggested_ocr_pages": analysis.get("suggested_ocr_pages", []),
            "material_type": meta.get("material_type"),
            "confidence": meta.get("confidence"),
            "extracted_data": meta.get("extracted_data"),
            "summary": meta.get("summary"),
            "ocr_text": analysis.get("combined_text") or analysis.get("full_text") or None,
            "suggested_doc_type": meta.get("suggested_doc_type"),
            "suggested_folder": meta.get("suggested_folder"),
            "doc_type": {"id": doc.doc_type.id, "name": doc.doc_type.name, "code": doc.doc_type.code}
                if doc.doc_type else None,
            "folder": {"id": doc.folder.id, "name": doc.folder.name, "path": doc.folder.path}
                if doc.folder else None,
        }


class OcrRequest(BaseModel):
    page_numbers: list[int]
    ocr_provider: Optional[str] = None  # Override: deepseek | bigmodel | paddleocr


@router.post("/process/{doc_id}/ocr", dependencies=[require_role("editor")])
async def trigger_ocr(doc_id: int, body: OcrRequest):
    """Trigger selective OCR on specific pages."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        proc_status = meta.get("_processing", {}).get("status")
        if proc_status not in ("analysis_done", "ocr_done", "classified", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot start OCR in current status: {proc_status}"
            )

    from dms_processor import run_ocr_phase
    thread = threading.Thread(
        target=run_ocr_phase,
        args=(doc_id, body.page_numbers),
        kwargs={"ocr_provider_override": body.ocr_provider},
        daemon=True,
    )
    thread.start()

    return {"status": "ocr_started", "pages": body.page_numbers, "provider": body.ocr_provider}


@router.post("/process/{doc_id}/classify", dependencies=[require_role("editor")])
async def trigger_classify(doc_id: int):
    """Trigger LLM classification after OCR is done."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        proc_status = meta.get("_processing", {}).get("status")
        if proc_status not in ("analysis_done", "ocr_done", "classified", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot classify in current status: {proc_status}"
            )

    from dms_processor import run_classify_phase
    thread = threading.Thread(
        target=run_classify_phase,
        args=(doc_id,),
        daemon=True,
    )
    thread.start()

    return {"status": "classifying"}


class MetadataUpdateRequest(BaseModel):
    title: Optional[str] = None
    material_type: Optional[str] = None
    doc_type_id: Optional[int] = None
    folder_id: Optional[int] = None
    extracted_data: Optional[dict] = None
    notes: Optional[str] = None


@router.put("/process/{doc_id}/metadata", dependencies=[require_role("editor")])
async def update_metadata(doc_id: int, body: MetadataUpdateRequest):
    """Update document metadata after human review."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if body.title is not None:
            doc.title = body.title
        if body.notes is not None:
            doc.description = body.notes
        if body.doc_type_id is not None:
            dt = session.query(DocType).filter(DocType.id == body.doc_type_id).first()
            if not dt:
                raise HTTPException(status_code=400, detail=f"DocType {body.doc_type_id} not found")
            doc.doc_type_id = body.doc_type_id
        if body.folder_id is not None:
            folder = session.query(Folder).filter(Folder.id == body.folder_id).first()
            if not folder:
                raise HTTPException(status_code=400, detail=f"Folder {body.folder_id} not found")
            doc.folder_id = body.folder_id

        # Update meta_json fields
        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        if body.material_type is not None:
            meta["material_type"] = body.material_type
        if body.extracted_data is not None:
            meta["extracted_data"] = body.extracted_data

        doc.meta_json = json.dumps(meta, ensure_ascii=False)
        session.flush()

        return {"success": True, "document_id": doc_id}


class FinalizeRequest(BaseModel):
    title: Optional[str] = None
    doc_type_id: Optional[int] = None
    folder_id: Optional[int] = None
    notes: Optional[str] = None


@router.post("/process/{doc_id}/finalize", dependencies=[require_role("editor")])
async def trigger_finalize(doc_id: int, body: FinalizeRequest = None, request: Request = None):
    """Finalize document: apply metadata corrections, run entity linking, set active."""
    if body is None:
        body = FinalizeRequest()

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status != "draft":
            raise HTTPException(status_code=409, detail="Only draft documents can be finalized")

        # Apply final corrections
        if body.title is not None:
            doc.title = body.title
        if body.doc_type_id is not None:
            dt = session.query(DocType).filter(DocType.id == body.doc_type_id).first()
            if not dt:
                raise HTTPException(status_code=400, detail=f"DocType {body.doc_type_id} not found")
            doc.doc_type_id = body.doc_type_id
        if body.folder_id is not None:
            folder = session.query(Folder).filter(Folder.id == body.folder_id).first()
            if not folder:
                raise HTTPException(status_code=400, detail=f"Folder {body.folder_id} not found")
            doc.folder_id = body.folder_id
        if body.notes is not None:
            doc.description = body.notes

        doc.status = "active"
        session.flush()

        # Learn type mapping if user chose a doc_type
        if body.doc_type_id is not None and dt:
            try:
                meta = {}
                if doc.meta_json:
                    meta = json.loads(doc.meta_json)
                material_type = meta.get("material_type", "")
                if material_type and material_type != "unknown":
                    from dms_processor import learn_type_mapping
                    learn_type_mapping(material_type, dt.code)
            except Exception:
                pass  # Non-critical

        uid = get_current_user_id(request) if request else None
        log_audit(session, uid, "approve", "document", doc.id, doc.title,
                  ip_address=request.client.host if request and request.client else None)

    # Run finalization in background (entity linking, expiry, version match, etc.)
    from dms_processor import finalize_document
    thread = threading.Thread(
        target=finalize_document,
        args=(doc_id,),
        daemon=True,
    )
    thread.start()

    return {"status": "finalizing", "document_id": doc_id}


# ============================================================
# Review Queue Endpoints
# ============================================================


@router.get("/queue")
async def list_queue(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List draft documents pending review."""
    with get_dms_session() as session:
        query = session.query(DmsDocument).filter(DmsDocument.status == "draft")
        total = query.count()
        docs = query.order_by(DmsDocument.created_at.desc()).offset(offset).limit(limit).all()

        results = []
        for doc in docs:
            # Get processing status from meta_json
            processing = {}
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                    processing = meta.get("_processing", {})
                except (json.JSONDecodeError, TypeError):
                    pass

            # Get thumbnail URL
            thumbnail_url = None
            cur_rev = doc.current_revision()
            if cur_rev:
                for f in cur_rev.files:
                    if f.file_type == "thumbnail":
                        thumbnail_url = f"/api/v2/files/{f.id}"
                        break

            results.append({
                "id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "doc_type": {"id": doc.doc_type.id, "name": doc.doc_type.name, "code": doc.doc_type.code} if doc.doc_type else None,
                "folder": {"id": doc.folder.id, "name": doc.folder.name, "path": doc.folder.path} if doc.folder else None,
                "processing_status": processing.get("status"),
                "thumbnail_url": thumbnail_url,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            })

        return {"results": results, "total": total, "offset": offset, "limit": limit}


class ApproveRequest(BaseModel):
    title: Optional[str] = None
    doc_type_id: Optional[int] = None
    folder_id: Optional[int] = None
    notes: Optional[str] = None
    kb_index: Optional[bool] = False  # Run KB chunking + embedding + event extraction


@router.post("/queue/{doc_id}/approve", dependencies=[require_role("editor")])
async def approve_document(doc_id: int, body: ApproveRequest = None, request: Request = None):
    """Approve a draft document, transitioning it to active status."""
    if body is None:
        body = ApproveRequest()

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status != "draft":
            raise HTTPException(status_code=409, detail="Invalid status transition: only draft documents can be approved")

        # Apply corrections
        if body.title is not None:
            doc.title = body.title
        if body.doc_type_id is not None:
            dt = session.query(DocType).filter(DocType.id == body.doc_type_id).first()
            if not dt:
                raise HTTPException(status_code=400, detail=f"DocType {body.doc_type_id} not found")
            doc.doc_type_id = body.doc_type_id
        if body.folder_id is not None:
            folder = session.query(Folder).filter(Folder.id == body.folder_id).first()
            if not folder:
                raise HTTPException(status_code=400, detail=f"Folder {body.folder_id} not found")
            doc.folder_id = body.folder_id
        if body.notes is not None:
            doc.description = body.notes

        doc.status = "active"
        session.flush()

        # Learn type mapping if user chose a doc_type for future auto-classification
        if body.doc_type_id is not None and dt:
            try:
                from dms_processor import learn_type_mapping
                meta_raw = doc.meta_json
                import json
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
                if isinstance(meta, dict) and meta.get("material_type"):
                    learn_type_mapping(meta["material_type"], dt.code)
            except Exception:
                pass

        uid = get_current_user_id(request) if request else None
        log_audit(session, uid, "approve", "document", doc.id, doc.title,
                  ip_address=request.client.host if request and request.client else None,
                  details={"action": "quick_approve", "kb_index": body.kb_index})

        result = doc.to_dict()

    # Run full background processing if KB indexing requested
    if body.kb_index:
        import threading
        t = threading.Thread(target=_run_full_finalize, args=(doc_id,), daemon=True)
        t.start()

    return result


def _run_full_finalize(doc_id: int):
    """Background: run finalize_document() for quick-approve with kb_index=True."""
    try:
        from dms_processor import finalize_document
        finalize_document(doc_id)
    except Exception as e:
        logger.warning(f"Background finalize failed for doc {doc_id}: {e}")


@router.get("/queue/{doc_id}/suggestions", dependencies=[require_role("editor")])
async def get_approve_suggestions(doc_id: int):
    """Get suggested doc_type and folder for the quick-approve panel.

    Returns suggestions based on:
    - Processing metadata (material_type, suggested_doc_type, suggested_folder)
    - Document content analysis (for audio/video with ASR text)
    """
    from dms_models import get_dms_session, DmsDocument
    import json

    result = {"doc_type": None, "folder": None, "suggestions": []}

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta_raw = doc.meta_json
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})

        # 1. Check for explicit suggestions from processing pipeline
        if isinstance(meta, dict):
            proc = meta.get("_processing", {}) or {}
            if isinstance(proc, str):
                proc = json.loads(proc)

            # Try suggested doc_type from LLM classification
            sug_type = meta.get("suggested_doc_type") or proc.get("suggested_doc_type")
            sug_folder = meta.get("suggested_folder") or proc.get("suggested_folder")
            material_type = meta.get("material_type") or proc.get("material_type")

            if sug_type:
                dt = session.query(DocType).filter(DocType.name == sug_type).first()
                if not dt:
                    dt = session.query(DocType).filter(DocType.code == sug_type).first()
                if dt:
                    result["doc_type"] = {"id": dt.id, "name": dt.name, "code": dt.code}

            if sug_folder:
                folder = session.query(Folder).filter(Folder.path == sug_folder).first()
                if not folder:
                    folder = session.query(Folder).filter(Folder.name == sug_folder).first()
                if folder:
                    result["folder"] = {"id": folder.id, "name": folder.name, "path": folder.path}

            if material_type and not result["doc_type"]:
                # Match material_type to doc_type
                from dms_processor import match_material_type
                dt_code = match_material_type(material_type)
                if dt_code:
                    dt = session.query(DocType).filter(DocType.code == dt_code).first()
                    if dt:
                        result["doc_type"] = {"id": dt.id, "name": dt.name, "code": dt.code}

        # 2. For audio/video: run LLM classification on ASR text if no suggestions yet
        if not result["doc_type"] and isinstance(meta, dict):
            asr_text = meta.get("asr_text")
            ocr_text = proc.get("ocr_text") if isinstance(proc, dict) else None
            text = asr_text or ocr_text or ""
            if text and len(text) > 100:
                try:
                    from ocr_agent import intelligent_extract
                    extraction = intelligent_extract(text, doc.title or "")
                    mt = extraction.get("material_type", "")
                    if mt:
                        result["material_type"] = mt
                        result["confidence"] = extraction.get("confidence", 0)

                        from dms_processor import match_material_type
                        dt_code = match_material_type(mt)
                        if dt_code:
                            dt = session.query(DocType).filter(DocType.code == dt_code).first()
                            if dt:
                                result["doc_type"] = {"id": dt.id, "name": dt.name, "code": dt.code}
                            from dms_processor import get_folder_path_for_doctype
                            f_path = get_folder_path_for_doctype(dt_code)
                            if f_path:
                                folder = session.query(Folder).filter(Folder.path == f_path).first()
                                if not folder:
                                    folder = session.query(Folder).filter(Folder.name == f_path).first()
                                if folder:
                                    result["folder"] = {"id": folder.id, "name": folder.name, "path": folder.path}

                        # Fuzzy match: find closest DocType by name similarity
                        if not result["doc_type"]:
                            all_types = session.query(DocType).all()
                            best_dt = None
                            best_score = 0
                            for dt in all_types:
                                # Simple overlap score
                                score = _name_similarity(mt, dt.name)
                                if score > best_score:
                                    best_score = score
                                    best_dt = dt
                            if best_dt and best_score >= 0.3:
                                result["doc_type"] = {
                                    "id": best_dt.id, "name": best_dt.name, "code": best_dt.code,
                                    "match_score": round(best_score, 2),
                                    "note": f"近似匹配 (AI识别: {mt})",
                                }

                        # Suggest folder by keyword in material_type
                        if not result["folder"]:
                            folder_hint = _guess_folder_from_text(mt + " " + doc.title)
                            if folder_hint:
                                folder = session.query(Folder).filter(
                                    (Folder.name == folder_hint) | (Folder.path.like(f"%{folder_hint}%"))
                                ).first()
                                if folder:
                                    result["folder"] = {"id": folder.id, "name": folder.name, "path": folder.path}
                except Exception as e:
                    logger.warning(f"Suggestion extraction failed for doc {doc_id}: {e}")

    return result


def _name_similarity(a: str, b: str) -> float:
    """Simple character-overlap similarity for Chinese names."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    overlap = len(set_a & set_b)
    return overlap / max(len(set_a | set_b), 1)


def _guess_folder_from_text(text: str) -> str:
    """Guess a folder name from keywords in text."""
    hints = {
        "培训": "培训资料", "会议": "会议记录", "录音": "会议记录",
        "合同": "合同", "证书": "资质", "认证": "iso认证及相关",
        "财务": "财务", "税务": "税务相关", "社保": "社保相关",
        "软件": "产品资料", "著作权": "产品资料", "视频": "培训资料",
    }
    for kw, folder in hints.items():
        if kw in text:
            return folder
    return ""


@router.post("/queue/{doc_id}/reject", dependencies=[require_role("editor")])
async def reject_document(
    doc_id: int,
    request: Request,
    delete: bool = Query(False),
):
    """Reject a draft document. Archives by default, deletes if delete=true."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status != "draft":
            raise HTTPException(status_code=409, detail="Invalid status transition: only draft documents can be rejected")

        uid = get_current_user_id(request)
        ip = request.client.host if request.client else None
        title = doc.title

        if delete:
            # Delete physical files
            for rev in doc.revisions:
                for f in rev.files:
                    file_path = DATA_DIR / f.storage_path
                    if file_path.exists():
                        file_path.unlink()
                # Remove revision directory
                rev_dir = DMS_FILES_DIR / str(doc.id) / str(rev.id)
                if rev_dir.exists():
                    import shutil
                    shutil.rmtree(str(rev_dir), ignore_errors=True)
            # Remove document directory
            doc_dir = DMS_FILES_DIR / str(doc.id)
            if doc_dir.exists():
                import shutil
                shutil.rmtree(str(doc_dir), ignore_errors=True)

            log_audit(session, uid, "reject", "document", doc_id, title,
                      details={"action": "deleted"}, ip_address=ip)
            session.delete(doc)
            return {"status": "deleted", "document_id": doc_id}
        else:
            doc.status = "archived"
            session.flush()
            log_audit(session, uid, "reject", "document", doc_id, title,
                      details={"action": "archived"}, ip_address=ip)
            return {"status": "archived", "document_id": doc_id}


class BatchRequest(BaseModel):
    action: str  # "approve" or "reject"
    document_ids: list[int]


# ============================================================
# Batch Upload
# ============================================================

@router.post("/batch", dependencies=[require_role("editor")])
async def batch_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    folder_id: Optional[int] = Form(None),
    doc_type_id: Optional[int] = Form(None),
):
    """Upload multiple files. Each file is processed independently."""
    results = []
    for file in files:
        try:
            # Read file content
            content = await file.read()
            file_hash = hashlib.md5(content).hexdigest()
            file_size = len(content)

            content_type = file.content_type or ""
            if content_type not in ALLOWED_MIME_TYPES:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": f"Unsupported type: {content_type}",
                })
                continue

            original_filename = file.filename or "untitled"
            title = Path(original_filename).stem

            # Duplicate check
            with get_dms_session() as session:
                existing = session.query(DmsFile).filter(
                    DmsFile.file_hash == file_hash, DmsFile.file_type == "original"
                ).first()
                if existing:
                    doc = existing.revision.document
                    results.append({
                        "filename": original_filename,
                        "success": False,
                        "error": "Duplicate",
                        "existing_document_id": doc.id,
                        "existing_title": doc.title,
                    })
                    continue

            # Create document + revision + file
            with get_dms_session() as session:
                processing_meta = {"_processing": {"status": "pending"}}
                doc = DmsDocument(
                    title=title,
                    status="draft",
                    folder_id=folder_id,
                    doc_type_id=doc_type_id,
                    meta_json=json.dumps(processing_meta, ensure_ascii=False),
                    created_by=get_current_user_id(request),
                )
                session.add(doc)
                session.flush()

                rev = Revision(document_id=doc.id, version_number=1, is_current=True)
                session.add(rev)
                session.flush()

                rev_dir = DMS_FILES_DIR / str(doc.id) / str(rev.id)
                rev_dir.mkdir(parents=True, exist_ok=True)
                safe_name = f"{file_hash[:8]}_{original_filename}"
                storage_path = f"dms_files/{doc.id}/{rev.id}/{safe_name}"
                full_path = DATA_DIR / storage_path
                with open(full_path, "wb") as f:
                    f.write(content)

                dms_file = DmsFile(
                    revision_id=rev.id,
                    file_type="original",
                    filename=original_filename,
                    storage_path=storage_path,
                    mime_type=content_type,
                    file_size=file_size,
                    file_hash=file_hash,
                )
                session.add(dms_file)
                session.flush()
                doc_id = doc.id

            # Background processing
            from dms_processor import analyze_document
            threading.Thread(target=analyze_document, args=(doc_id,), daemon=True).start()

            results.append({
                "filename": original_filename,
                "success": True,
                "document_id": doc_id,
                "status": "processing",
            })

        except Exception as e:
            logger.exception(f"Batch upload error for {file.filename}: {e}")
            results.append({
                "filename": file.filename or "unknown",
                "success": False,
                "error": str(e),
            })

    return {
        "total": len(files),
        "succeeded": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results,
    }


# ============================================================
# PDF Rotation
# ============================================================

class RotateRequest(BaseModel):
    direction: str = "right"  # "left" or "right"


@router.post("/process/{doc_id}/rotate", dependencies=[require_role("editor")])
async def rotate_pdf(doc_id: int, body: RotateRequest = None):
    """Rotate all pages of a PDF document 90° left or right.

    Rewrites the stored file and clears cached thumbnails so they are regenerated.
    """
    if body is None:
        body = RotateRequest()

    if body.direction not in ("left", "right"):
        raise HTTPException(status_code=400, detail="direction must be 'left' or 'right'")

    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise HTTPException(status_code=500, detail="PyMuPDF not installed")

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        cur_rev = doc.current_revision()
        if not cur_rev:
            raise HTTPException(status_code=404, detail="No current revision")

        original_file = None
        for f in cur_rev.files:
            if f.file_type == "original":
                original_file = f
                break

        if not original_file:
            raise HTTPException(status_code=404, detail="No original file found")

        full_path = DATA_DIR / original_file.storage_path
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found on disk: {full_path}")

        mime = original_file.mime_type or ""
        if "pdf" not in mime and full_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Rotation is only supported for PDF files")

        # Rotate using PyMuPDF (save to temp then replace)
        rotation_angle = 90 if body.direction == "right" else -90
        pdf_doc = fitz.open(str(full_path))
        total_pages = len(pdf_doc)

        for page in pdf_doc:
            page.set_rotation(page.rotation + rotation_angle)

        # Save to temp file, then replace original
        tmp_path = full_path.with_suffix(".rotated_tmp.pdf")
        pdf_doc.save(str(tmp_path), incremental=False)
        pdf_doc.close()
        tmp_path.replace(full_path)

        # Clear cached thumbnails so they regenerate on next request
        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        analysis = meta.get("_analysis", {})
        for p in analysis.get("pages", []):
            # Remove old thumbnail so it regenerates
            old_thumb = p.pop("thumbnail_path", None)
            if old_thumb:
                thumb_path = DATA_DIR / old_thumb
                if thumb_path.exists():
                    thumb_path.unlink()

        doc.meta_json = json.dumps(meta, ensure_ascii=False)
        session.flush()

        return {
            "status": "rotated",
            "document_id": doc_id,
            "direction": body.direction,
            "total_pages": total_pages,
            "message": f"PDF rotated {body.direction} (thumbnails cleared, will regenerate)",
        }


# ============================================================
# Thumbnail with Rotation Support
# ============================================================


@router.get("/process/{doc_id}/page/{page_num}/thumb")
async def get_page_thumbnail(
    doc_id: int,
    page_num: int,
    rotation: int = Query(0, description="Rotation override in degrees (0, 90, 180, 270)"),
):
    """Serve a page thumbnail image with optional rotation override."""
    from fastapi.responses import FileResponse
    from PIL import Image as PILImage
    import io

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        analysis = meta.get("_analysis", {})
        for p in analysis.get("pages", []):
            if p["page_num"] == page_num and p.get("thumbnail_path"):
                full_path = DATA_DIR / p["thumbnail_path"]
                if not full_path.exists():
                    break

                # Return as-is if no rotation requested
                if rotation not in (90, 180, 270):
                    return FileResponse(str(full_path), media_type="image/png")

                # Apply on-the-fly rotation
                img = PILImage.open(str(full_path))
                if rotation == 90:
                    img = img.transpose(PILImage.ROTATE_270)
                elif rotation == 180:
                    img = img.rotate(180, expand=True)
                elif rotation == 270:
                    img = img.transpose(PILImage.ROTATE_90)

                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                from fastapi.responses import StreamingResponse
                return StreamingResponse(buf, media_type="image/png")

    raise HTTPException(status_code=404, detail="Thumbnail not found")


@router.post("/queue/batch", dependencies=[require_role("editor")])
async def batch_action(body: BatchRequest):
    """Batch approve or reject multiple documents."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    results = []
    with get_dms_session() as session:
        for doc_id in body.document_ids:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                results.append({"document_id": doc_id, "success": False, "error": "Not found"})
                continue

            if doc.status != "draft":
                results.append({"document_id": doc_id, "success": False, "error": "Not in draft status"})
                continue

            if body.action == "approve":
                doc.status = "active"
            else:
                doc.status = "archived"

            results.append({"document_id": doc_id, "success": True})

    return {"results": results}


# ============================================================
# Merge Confirmation
# ============================================================

class MergeConfirmRequest(BaseModel):
    action: str  # "confirm" or "reject"


@router.post("/process/{doc_id}/merge-confirm", dependencies=[require_role("editor")])
async def confirm_merge(doc_id: int, body: MergeConfirmRequest):
    """Confirm or reject a pending version merge.

    When a new upload matches an existing document (same entity + type + cert identity),
    the system pauses for user confirmation instead of auto-merging.

    - confirm: merges the new doc as a new revision on the existing doc
    - reject:  removes the pending flag, keeps both as separate documents
    """
    if body.action not in ("confirm", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'confirm' or 'reject'")

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        pending = meta.pop("_pending_merge", None)
        if not pending:
            raise HTTPException(status_code=400, detail="No pending merge for this document")

        existing_id = pending["existing_doc_id"]

        if body.action == "confirm":
            from dms_version_matcher import merge_as_revision
            success = merge_as_revision(existing_id, doc_id, session)
            if success:
                return {"status": "merged", "into_doc_id": existing_id}
            else:
                raise HTTPException(status_code=500, detail="Merge failed")

        else:  # reject
            # Keep as separate document, just clear the pending flag
            doc.meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
            return {"status": "kept_separate", "document_id": doc_id}

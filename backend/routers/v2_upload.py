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
    # Validate MIME type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. "
                   f"Allowed: PDF, JPEG, PNG, TIFF, DOCX, DOC",
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


@router.get("/process/{doc_id}/page/{page_num}/thumb")
async def get_page_thumbnail(doc_id: int, page_num: int):
    """Serve a page thumbnail image."""
    from fastapi.responses import FileResponse

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
                if full_path.exists():
                    return FileResponse(str(full_path), media_type="image/png")

    raise HTTPException(status_code=404, detail="Thumbnail not found")


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

        uid = get_current_user_id(request) if request else None
        log_audit(session, uid, "approve", "document", doc.id, doc.title,
                  ip_address=request.client.host if request and request.client else None)

        return doc.to_dict()


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

"""DMS Document & Revision API endpoints."""

import json
import hashlib
import logging
import os
import threading
from datetime import date, datetime, timedelta
from typing import Optional, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from pydantic import BaseModel

from dms_auth import require_role, get_current_user_id, get_accessible_folder_ids
from dms_audit import log_audit

from dms_models import (
    get_dms_session, DmsDocument, Revision, DmsFile, Folder, DocType,
    Entity, DocumentEntity, Tag, DocumentTag, VALID_STATUS_TRANSITIONS,
)

logger = logging.getLogger("materialhub.routers.v2_documents")

router = APIRouter(prefix="/api/v2/documents", tags=["dms-documents"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))

LOCK_TIMEOUT_MINUTES = 30


def _is_locked(doc) -> bool:
    """Check if document has an active (non-expired) lock."""
    if not doc.locked_by:
        return False
    if not doc.locked_at:
        return False
    return (datetime.utcnow() - doc.locked_at) < timedelta(minutes=LOCK_TIMEOUT_MINUTES)


def _lock_info(doc) -> dict:
    """Build lock status dict for API responses."""
    is_locked = _is_locked(doc)
    return {
        "locked_by": doc.locked_by if is_locked else None,
        "locked_at": doc.locked_at.isoformat() if (is_locked and doc.locked_at) else None,
        "is_locked": is_locked,
    }


def _check_lock(doc, user_id: int):
    """Raise 409 if document is locked by another user."""
    if _is_locked(doc) and doc.locked_by != user_id:
        raise HTTPException(status_code=409, detail="Document is locked by another user")


# ============================================================
# Request schemas
# ============================================================

class DocumentCreate(BaseModel):
    folder_id: int
    doc_type_id: int
    title: str
    description: Optional[str] = None
    metadata: Optional[Any] = None
    expiry_date: Optional[str] = None  # ISO format date string
    status: Optional[str] = "draft"


class DocumentUpdate(BaseModel):
    folder_id: Optional[int] = None
    doc_type_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Any] = None
    expiry_date: Optional[str] = None
    status: Optional[str] = None


class RevisionCreate(BaseModel):
    change_note: Optional[str] = None


class EntityLinkCreate(BaseModel):
    entity_id: int
    role: str  # owner/issuer/subject/related


class TagLinkCreate(BaseModel):
    tag_id: int


# ============================================================
# Document endpoints
# ============================================================

@router.post("/", dependencies=[require_role("editor")])
async def create_document(data: DocumentCreate, request: Request):
    """Create a new document with an initial revision."""
    with get_dms_session() as session:
        # Validate folder
        folder = session.query(Folder).filter(Folder.id == data.folder_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Validate doc type
        doc_type = session.query(DocType).filter(DocType.id == data.doc_type_id).first()
        if not doc_type:
            raise HTTPException(status_code=404, detail="DocType not found")

        # Parse expiry date
        expiry = None
        if data.expiry_date:
            try:
                expiry = date.fromisoformat(data.expiry_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid expiry_date format. Use YYYY-MM-DD.")

        # Create document
        meta_str = json.dumps(data.metadata, ensure_ascii=False) if data.metadata else None
        doc = DmsDocument(
            folder_id=data.folder_id,
            doc_type_id=data.doc_type_id,
            title=data.title,
            description=data.description,
            status=data.status or "draft",
            meta_json=meta_str,
            expiry_date=expiry,
            created_by=get_current_user_id(request),
        )
        session.add(doc)
        session.flush()

        # Create initial revision
        rev = Revision(
            document_id=doc.id,
            version_number=1,
            is_current=True,
            change_note="Initial version",
            created_by=get_current_user_id(request),
        )
        session.add(rev)
        session.flush()

        log_audit(session, get_current_user_id(request), "create", "document",
                  doc.id, doc.title, ip_address=request.client.host if request.client else None)

        return doc.to_dict()


@router.get("/")
async def list_documents(
    request: Request,
    folder_id: Optional[int] = Query(None),
    doc_type_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    tag_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List documents with multiple filter options."""
    allowed_folders = get_accessible_folder_ids(request)

    with get_dms_session() as session:
        query = session.query(DmsDocument)

        # Folder-level access control
        if allowed_folders is not None:
            if not allowed_folders:
                return {"results": [], "total": 0, "limit": limit, "offset": offset}
            query = query.filter(DmsDocument.folder_id.in_(allowed_folders))

        if folder_id is not None:
            # Include documents in the selected folder AND all sub-folders
            folder = session.query(Folder).filter(Folder.id == folder_id).first()
            if folder:
                sub_ids = [r[0] for r in session.query(Folder.id).filter(
                    Folder.path.like(f"{folder.path}%")
                ).all()]
                query = query.filter(DmsDocument.folder_id.in_(sub_ids))
            else:
                query = query.filter(DmsDocument.folder_id == folder_id)

        if doc_type_id is not None:
            query = query.filter(DmsDocument.doc_type_id == doc_type_id)

        if status:
            if status == "expired":
                # Include both explicitly expired and past-expiry-date documents
                today = date.today()
                query = query.filter(
                    (DmsDocument.status == "expired") |
                    ((DmsDocument.expiry_date.isnot(None)) & (DmsDocument.expiry_date < today))
                )
            else:
                query = query.filter(DmsDocument.status == status)

        if entity_id is not None:
            query = query.join(DocumentEntity).filter(DocumentEntity.entity_id == entity_id)

        if tag_id is not None:
            query = query.join(DocumentTag).filter(DocumentTag.tag_id == tag_id)

        if q:
            keyword = f"%{q}%"
            query = query.filter(DmsDocument.title.ilike(keyword))

        total = query.count()
        docs = query.order_by(DmsDocument.updated_at.desc()).offset(offset).limit(limit).all()

        return {
            "results": [d.to_dict(include_revision=True, include_relations=True) for d in docs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/{doc_id}")
async def get_document(doc_id: int, request: Request):
    """Get document detail with current revision, entities, and tags."""
    allowed_folders = get_accessible_folder_ids(request)

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if allowed_folders is not None and doc.folder_id not in allowed_folders:
            raise HTTPException(status_code=403, detail="No access to this document")
        result = doc.to_dict(include_revision=True, include_relations=True)
        result["lock"] = _lock_info(doc)
        return result


@router.get("/{doc_id}/metadata.json")
async def export_metadata(doc_id: int, request: Request):
    """Export document metadata as a downloadable JSON file."""
    from fastapi.responses import Response

    allowed_folders = get_accessible_folder_ids(request)

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if allowed_folders is not None and doc.folder_id not in allowed_folders:
            raise HTTPException(status_code=403, detail="No access to this document")

        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        export = {
            "document_id": doc.id,
            "title": doc.title,
            "status": doc.status,
            "doc_type": doc.doc_type.name if doc.doc_type else None,
            "doc_type_code": doc.doc_type.code if doc.doc_type else None,
            "folder": doc.folder.path if doc.folder else None,
            "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            "material_type": meta.get("material_type"),
            "confidence": meta.get("confidence"),
            "summary": meta.get("summary"),
            "extracted_data": meta.get("extracted_data", {}),
            "entities": [
                {"name": el.entity.name, "type": el.entity.entity_type, "role": el.role}
                for el in doc.entity_links if el.entity
            ],
            "tags": [tl.tag.name for tl in doc.tag_links if tl.tag],
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }

        content = json.dumps(export, ensure_ascii=False, indent=2)
        safe_title = doc.title.replace("/", "_").replace("\\", "_")[:50]
        filename = f"{safe_title}_metadata.json"
        # URL-encode filename for Content-Disposition (RFC 5987)
        from urllib.parse import quote
        encoded = quote(filename)

        return Response(
            content=content.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            },
        )


@router.patch("/{doc_id}", dependencies=[require_role("editor")])
async def update_document(doc_id: int, data: DocumentUpdate, request: Request):
    """Update document fields with status transition validation."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Lock check: reject if locked by another user
        _check_lock(doc, get_current_user_id(request))

        update_data = data.model_dump(exclude_unset=True)
        old_status = doc.status

        # Status transition validation
        if "status" in update_data:
            new_status = update_data["status"]
            if not doc.can_transition_to(new_status):
                allowed = VALID_STATUS_TRANSITIONS.get(doc.status, set())
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid status transition: {doc.status} -> {new_status}. Allowed: {allowed}"
                )
            doc.status = new_status
            update_data.pop("status")

        # Validate references
        if "folder_id" in update_data:
            folder = session.query(Folder).filter(Folder.id == update_data["folder_id"]).first()
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

        if "doc_type_id" in update_data:
            dt = session.query(DocType).filter(DocType.id == update_data["doc_type_id"]).first()
            if not dt:
                raise HTTPException(status_code=404, detail="DocType not found")

        # Handle metadata
        if "metadata" in update_data:
            val = update_data.pop("metadata")
            doc.meta_json = json.dumps(val, ensure_ascii=False) if val is not None else None

        # Handle expiry_date
        if "expiry_date" in update_data:
            val = update_data.pop("expiry_date")
            if val:
                try:
                    doc.expiry_date = date.fromisoformat(val)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid expiry_date format")
            else:
                doc.expiry_date = None

        for field, value in update_data.items():
            setattr(doc, field, value)

        session.flush()

        # Audit logging
        uid = get_current_user_id(request)
        ip = request.client.host if request.client else None
        if old_status != doc.status:
            log_audit(session, uid, "status_change", "document", doc.id, doc.title,
                      details={"old_status": old_status, "new_status": doc.status}, ip_address=ip)
        else:
            log_audit(session, uid, "update", "document", doc.id, doc.title, ip_address=ip)

        return doc.to_dict()


@router.delete("/{doc_id}", dependencies=[require_role("editor")])
async def delete_document(doc_id: int, request: Request):
    """Delete document and cascade to revisions, files, and associations."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete physical files
        for rev in doc.revisions:
            for f in rev.files:
                try:
                    file_path = DATA_DIR / f.storage_path
                    if file_path.exists():
                        file_path.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete file {f.storage_path}: {e}")

        title = doc.title
        log_audit(session, get_current_user_id(request), "delete", "document",
                  doc_id, title, ip_address=request.client.host if request.client else None)
        session.delete(doc)  # Cascade handles revisions, files, entity/tag links
        return {"success": True, "deleted": title}


# ============================================================
# Lock endpoints
# ============================================================

@router.post("/{doc_id}/lock", dependencies=[require_role("editor")])
async def lock_document(doc_id: int, request: Request):
    """Acquire or renew an advisory lock on a document."""
    user_id = get_current_user_id(request)
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if _is_locked(doc) and doc.locked_by != user_id:
            raise HTTPException(status_code=409, detail="Document is locked by another user")

        doc.locked_by = user_id
        doc.locked_at = datetime.utcnow()
        session.flush()

        log_audit(session, user_id, "lock", "document", doc.id, doc.title,
                  ip_address=request.client.host if request.client else None)

        return {"success": True, "lock": _lock_info(doc)}


@router.post("/{doc_id}/unlock", dependencies=[require_role("editor")])
async def unlock_document(doc_id: int, request: Request):
    """Release a lock. Lock holder or admin can unlock."""
    user_id = get_current_user_id(request)
    user_role = getattr(request.state, "user_role", "editor")

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if not _is_locked(doc):
            return {"success": True, "message": "Document was not locked"}

        # Only lock holder or admin can unlock
        if doc.locked_by != user_id and user_role != "admin":
            raise HTTPException(status_code=403, detail="Only the lock holder or an admin can unlock")

        doc.locked_by = None
        doc.locked_at = None
        session.flush()

        log_audit(session, user_id, "unlock", "document", doc.id, doc.title,
                  ip_address=request.client.host if request.client else None)

        return {"success": True, "lock": _lock_info(doc)}


# ============================================================
# Revision endpoints
# ============================================================

@router.get("/{doc_id}/revisions/")
async def list_revisions(doc_id: int):
    """List all revisions for a document."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        revisions = session.query(Revision).filter(
            Revision.document_id == doc_id
        ).order_by(Revision.version_number.desc()).all()

        return {"revisions": [r.to_dict() for r in revisions]}


@router.post("/{doc_id}/revisions/", dependencies=[require_role("editor")])
async def create_revision(doc_id: int, data: RevisionCreate, request: Request):
    """Create a new revision, marking previous ones as non-current."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Get max version number
        max_ver = session.query(Revision.version_number).filter(
            Revision.document_id == doc_id
        ).order_by(Revision.version_number.desc()).first()
        next_ver = (max_ver[0] + 1) if max_ver else 1

        # Mark all existing revisions as non-current
        session.query(Revision).filter(
            Revision.document_id == doc_id
        ).update({"is_current": False})

        rev = Revision(
            document_id=doc_id,
            version_number=next_ver,
            is_current=True,
            change_note=data.change_note,
            created_by=get_current_user_id(request),
        )
        session.add(rev)
        session.flush()
        return rev.to_dict()


@router.get("/{doc_id}/revisions/{rev_id}")
async def get_revision(doc_id: int, rev_id: int):
    """Get a specific revision with its files."""
    with get_dms_session() as session:
        rev = session.query(Revision).filter(
            Revision.id == rev_id,
            Revision.document_id == doc_id,
        ).first()
        if not rev:
            raise HTTPException(status_code=404, detail="Revision not found")
        return rev.to_dict()


# ============================================================
# Document-Entity link endpoints
# ============================================================

@router.post("/{doc_id}/entities/", dependencies=[require_role("editor")])
async def link_entity(doc_id: int, data: EntityLinkCreate):
    """Link an entity to a document with a role."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        entity = session.query(Entity).filter(Entity.id == data.entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        # Check for existing link with same role
        existing = session.query(DocumentEntity).filter(
            DocumentEntity.document_id == doc_id,
            DocumentEntity.entity_id == data.entity_id,
            DocumentEntity.role == data.role,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Entity already linked with this role")

        link = DocumentEntity(
            document_id=doc_id,
            entity_id=data.entity_id,
            role=data.role,
        )
        session.add(link)
        session.flush()
        return link.to_dict()


@router.delete("/{doc_id}/entities/{entity_id}", dependencies=[require_role("editor")])
async def unlink_entity(doc_id: int, entity_id: int):
    """Remove entity-document association."""
    with get_dms_session() as session:
        links = session.query(DocumentEntity).filter(
            DocumentEntity.document_id == doc_id,
            DocumentEntity.entity_id == entity_id,
        ).all()
        if not links:
            raise HTTPException(status_code=404, detail="Entity link not found")

        for link in links:
            session.delete(link)
        return {"success": True}


# ============================================================
# Document-Tag link endpoints
# ============================================================

@router.post("/{doc_id}/tags/", dependencies=[require_role("editor")])
async def add_tag(doc_id: int, data: TagLinkCreate):
    """Add a tag to a document."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        tag = session.query(Tag).filter(Tag.id == data.tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")

        existing = session.query(DocumentTag).filter(
            DocumentTag.document_id == doc_id,
            DocumentTag.tag_id == data.tag_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Tag already added to this document")

        link = DocumentTag(document_id=doc_id, tag_id=data.tag_id)
        session.add(link)
        session.flush()
        return link.to_dict()


@router.delete("/{doc_id}/tags/{tag_id}", dependencies=[require_role("editor")])
async def remove_tag(doc_id: int, tag_id: int):
    """Remove a tag from a document."""
    with get_dms_session() as session:
        link = session.query(DocumentTag).filter(
            DocumentTag.document_id == doc_id,
            DocumentTag.tag_id == tag_id,
        ).first()
        if not link:
            raise HTTPException(status_code=404, detail="Tag link not found")

        session.delete(link)
        return {"success": True}


# ============================================================
# Direct Import (for MCP / programmatic use)
# ============================================================

DMS_FILES_DIR = DATA_DIR / "dms_files"

IMPORT_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


@router.post("/actions/import", dependencies=[require_role("editor")])
async def import_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type_code: Optional[str] = Form(None),
    doc_type_id: Optional[int] = Form(None),
    folder_path: Optional[str] = Form(None),
    folder_id: Optional[int] = Form(None),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    entity_names: Optional[str] = Form(None),
    extracted_data: Optional[str] = Form(None),
    material_type: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    confidence: Optional[float] = Form(None),
    force: Optional[bool] = Form(False),
):
    """Direct import: upload file with classification results, create active document.

    Accepts doc_type by code or ID, folder by path or ID.
    Runs entity linking and FTS indexing in background.
    Designed for MCP agents that perform analysis client-side.
    """
    # Validate MIME
    content_type = file.content_type or ""
    if content_type not in IMPORT_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()
    file_size = len(content)

    # Duplicate check
    if not force:
        with get_dms_session() as session:
            existing = session.query(DmsFile).filter(
                DmsFile.file_hash == file_hash, DmsFile.file_type == "original",
            ).first()
            if existing:
                doc = existing.revision.document
                raise HTTPException(status_code=409, detail=json.dumps({
                    "code": "DUPLICATE_FILE",
                    "message": f"文件已存在: {doc.title}",
                    "existing_document": {
                        "id": doc.id, "title": doc.title, "status": doc.status,
                    },
                }, ensure_ascii=False))

    # Folder-level access control
    allowed_folders = get_accessible_folder_ids(request)

    # Get user/agent identity (agent has no user_id)
    caller_id = getattr(request.state, "user_id", None)
    agent_id = getattr(request.state, "agent_id", None)

    with get_dms_session() as session:
        # Resolve doc_type (by ID or code/name)
        resolved_doc_type_id = doc_type_id
        if not resolved_doc_type_id and doc_type_code:
            dt = session.query(DocType).filter(DocType.code == doc_type_code).first()
            if not dt:
                dt = session.query(DocType).filter(DocType.name == doc_type_code).first()
            if dt:
                resolved_doc_type_id = dt.id
            else:
                raise HTTPException(status_code=400, detail=f"Unknown doc_type: {doc_type_code}")

        if resolved_doc_type_id:
            if not session.query(DocType).filter(DocType.id == resolved_doc_type_id).first():
                raise HTTPException(status_code=400, detail=f"DocType ID {resolved_doc_type_id} not found")

        # Resolve folder (by ID or path/name)
        resolved_folder_id = folder_id
        if not resolved_folder_id and folder_path:
            folder = session.query(Folder).filter(Folder.path == folder_path).first()
            if not folder:
                folder = session.query(Folder).filter(Folder.name == folder_path).first()
            if folder:
                resolved_folder_id = folder.id
            else:
                raise HTTPException(status_code=400, detail=f"Unknown folder: {folder_path}")

        if resolved_folder_id:
            if not session.query(Folder).filter(Folder.id == resolved_folder_id).first():
                raise HTTPException(status_code=400, detail=f"Folder ID {resolved_folder_id} not found")

        # Folder permission enforcement for restricted users/agents
        if allowed_folders is not None:
            if not allowed_folders:
                raise HTTPException(status_code=403, detail="No folder access assigned")

            if resolved_folder_id:
                # Caller specified a folder — must be in allowed list
                if resolved_folder_id not in allowed_folders:
                    allowed_names = []
                    for fid in allowed_folders:
                        f = session.query(Folder).filter(Folder.id == fid).first()
                        if f:
                            allowed_names.append(f"{f.name} ({f.path})")
                    raise HTTPException(
                        status_code=403,
                        detail=f"No permission for this folder. Allowed: {', '.join(allowed_names)}",
                    )
            else:
                # Caller didn't specify folder — auto-assign if agent has exactly one root folder
                from dms_models import AgentFolderAccess
                if agent_id is not None:
                    root_ids = [r[0] for r in session.query(AgentFolderAccess.folder_id).filter(
                        AgentFolderAccess.agent_id == agent_id,
                    ).all()]
                    if len(root_ids) == 1:
                        resolved_folder_id = root_ids[0]
                    else:
                        folder_opts = []
                        for fid in root_ids:
                            f = session.query(Folder).filter(Folder.id == fid).first()
                            if f:
                                folder_opts.append(f"{f.name} ({f.path})")
                        raise HTTPException(
                            status_code=400,
                            detail=f"Agent has multiple folders, must specify one: {', '.join(folder_opts)}",
                        )
                else:
                    raise HTTPException(status_code=400, detail="Folder is required")

        # Parse expiry date
        expiry = None
        if expiry_date:
            try:
                expiry = date.fromisoformat(expiry_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid expiry_date, use YYYY-MM-DD")

        # Parse extracted_data JSON
        ext_data = {}
        if extracted_data:
            try:
                ext_data = json.loads(extracted_data)
            except (json.JSONDecodeError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid extracted_data JSON")

        # Build metadata
        meta = {}
        if material_type:
            meta["material_type"] = material_type
        if summary:
            meta["summary"] = summary
        if confidence is not None:
            meta["confidence"] = confidence
        if ext_data:
            meta["extracted_data"] = ext_data
        meta["_processing"] = {"status": "completed", "import_mode": "direct"}

        # Create document (directly active)
        doc = DmsDocument(
            title=title,
            status="active",
            folder_id=resolved_folder_id,
            doc_type_id=resolved_doc_type_id,
            description=description,
            expiry_date=expiry,
            meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
            created_by=caller_id,
        )
        session.add(doc)
        session.flush()

        # Create revision
        rev = Revision(
            document_id=doc.id,
            version_number=1,
            is_current=True,
            change_note=f"Direct import{f' via agent {agent_id}' if agent_id else ''}",
            created_by=caller_id,
        )
        session.add(rev)
        session.flush()

        # Store file
        original_filename = file.filename or "untitled"
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
        log_audit(session, caller_id, "import", "document",
                  doc.id, doc.title,
                  details={"agent_id": agent_id} if agent_id else None,
                  ip_address=request.client.host if request.client else None)

    logger.info(f"Direct import: doc={doc_id}, title={title}, file={file.filename}")

    # Background: entity linking, FTS indexing, expiry, version match
    from dms_processor import finalize_document
    thread = threading.Thread(target=finalize_document, args=(doc_id,), daemon=True)
    thread.start()

    # Return created document
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        return doc.to_dict()


# ============================================================
# Batch Reprocess (OCR + LLM re-extraction)
# ============================================================

class ReprocessRequest(BaseModel):
    doc_ids: list[int]
    force: bool = False  # True = overwrite existing metadata


@router.post("/actions/reprocess-check", dependencies=[require_role("editor")])
async def reprocess_check(req: ReprocessRequest, request: Request):
    """Check metadata status for documents before reprocessing.

    Returns each document's metadata status so the UI can warn about overwrites.
    """

    results = []
    with get_dms_session() as session:
        for doc_id in req.doc_ids:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                results.append({"id": doc_id, "title": "未找到", "status": "not_found", "has_metadata": False})
                continue

            has_metadata = False
            has_file = False
            metadata_fields = []

            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                    extracted = meta.get("extracted_data", {})
                    if isinstance(extracted, dict) and extracted:
                        has_metadata = True
                        metadata_fields = [k for k, v in extracted.items() if v]
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check if original file exists
            cur_rev = doc.current_revision()
            if cur_rev:
                for f in cur_rev.files:
                    if f.file_type == "original":
                        has_file = True
                        break

            results.append({
                "id": doc.id,
                "title": doc.title,
                "doc_type": doc.doc_type.name if doc.doc_type else None,
                "has_metadata": has_metadata,
                "metadata_fields": metadata_fields,
                "has_file": has_file,
                "summary": json.loads(doc.meta_json).get("summary", "") if doc.meta_json else "",
            })

    return {"documents": results}


@router.post("/actions/reprocess", dependencies=[require_role("editor")])
async def reprocess_documents(req: ReprocessRequest, request: Request):
    """Trigger OCR + LLM re-extraction for selected documents.

    If force=False, only processes documents without existing extracted_data.
    If force=True, reprocesses all selected documents (overwrites metadata).
    """

    queued = []
    skipped = []

    with get_dms_session() as session:
        for doc_id in req.doc_ids:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                skipped.append({"id": doc_id, "reason": "not_found"})
                continue

            # Check if has existing metadata
            if not req.force and doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                    extracted = meta.get("extracted_data", {})
                    if isinstance(extracted, dict) and extracted:
                        skipped.append({"id": doc_id, "reason": "has_metadata"})
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            queued.append(doc_id)

    # Launch background processing for each document
    from dms_processor import process_document

    for doc_id in queued:
        thread = threading.Thread(target=process_document, args=(doc_id,), daemon=True)
        thread.start()

    return {
        "queued": len(queued),
        "skipped": len(skipped),
        "queued_ids": queued,
        "skipped_details": skipped,
    }

"""DMS Bid Requirement API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from dms_models import (
    get_dms_session, BidProject, BidRequirement, BidDocument,
    DmsDocument, DocType,
)
from dms_auth import require_role, get_current_user_id

logger = logging.getLogger("materialhub.routers.v2_bid_requirements")

router = APIRouter(prefix="/api/v2/bids", tags=["dms-bid-requirements"])


# ============================================================
# Request schemas
# ============================================================

class RequirementCreate(BaseModel):
    title: str
    doc_type_id: Optional[int] = None
    description: Optional[str] = None
    is_required: bool = True
    sort_order: int = 0


class RequirementUpdate(BaseModel):
    title: Optional[str] = None
    doc_type_id: Optional[int] = None
    description: Optional[str] = None
    is_required: Optional[bool] = None
    sort_order: Optional[int] = None


class CategoryRequest(BaseModel):
    category: str


class LinkDocumentRequest(BaseModel):
    document_id: int
    notes: Optional[str] = None


class UpdateBidDocStatus(BaseModel):
    status: str  # "verified"


# ============================================================
# Helpers
# ============================================================

def _get_bid_or_404(session, bid_id: int) -> BidProject:
    project = session.query(BidProject).filter(BidProject.id == bid_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Bid project not found")
    return project


def _get_requirement_or_404(session, bid_id: int, req_id: int) -> BidRequirement:
    req = session.query(BidRequirement).filter(
        BidRequirement.id == req_id,
        BidRequirement.bid_project_id == bid_id,
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


def _requirement_with_fulfillment(session, req: BidRequirement) -> dict:
    """Build requirement dict with linked documents and fulfillment status."""
    d = req.to_dict()
    linked_docs = []
    fulfilled = False
    for bd in req.bid_documents:
        doc = session.query(DmsDocument).filter(DmsDocument.id == bd.document_id).first()
        bd_dict = bd.to_dict()
        bd_dict["document_exists"] = doc is not None
        if doc:
            bd_dict["document_status"] = doc.status
            fulfilled = True
        linked_docs.append(bd_dict)
    d["linked_documents"] = linked_docs
    d["fulfilled"] = fulfilled
    return d


# ============================================================
# Requirement CRUD
# ============================================================

@router.post("/{bid_id}/requirements", dependencies=[require_role("editor")])
async def create_requirement(bid_id: int, data: RequirementCreate):
    """Create a document requirement for a bid project."""
    with get_dms_session() as session:
        _get_bid_or_404(session, bid_id)

        if data.doc_type_id is not None:
            dt = session.query(DocType).filter(DocType.id == data.doc_type_id).first()
            if not dt:
                raise HTTPException(status_code=400, detail=f"DocType {data.doc_type_id} not found")

        req = BidRequirement(
            bid_project_id=bid_id,
            doc_type_id=data.doc_type_id,
            title=data.title,
            description=data.description,
            is_required=data.is_required,
            sort_order=data.sort_order,
        )
        session.add(req)
        session.flush()
        return req.to_dict()


@router.get("/{bid_id}/requirements")
async def list_requirements(bid_id: int):
    """List requirements with linked documents and fulfillment status."""
    with get_dms_session() as session:
        _get_bid_or_404(session, bid_id)

        reqs = session.query(BidRequirement).filter(
            BidRequirement.bid_project_id == bid_id
        ).order_by(BidRequirement.sort_order, BidRequirement.id).all()

        results = [_requirement_with_fulfillment(session, req) for req in reqs]
        return {"requirements": results, "total": len(results)}


@router.patch("/{bid_id}/requirements/{req_id}", dependencies=[require_role("editor")])
async def update_requirement(bid_id: int, req_id: int, data: RequirementUpdate):
    """Update requirement fields."""
    with get_dms_session() as session:
        req = _get_requirement_or_404(session, bid_id, req_id)

        update_data = data.model_dump(exclude_unset=True)
        if "doc_type_id" in update_data and update_data["doc_type_id"] is not None:
            dt = session.query(DocType).filter(DocType.id == update_data["doc_type_id"]).first()
            if not dt:
                raise HTTPException(status_code=400, detail="DocType not found")

        for field, value in update_data.items():
            setattr(req, field, value)

        session.flush()
        return req.to_dict()


@router.delete("/{bid_id}/requirements/{req_id}", dependencies=[require_role("editor")])
async def delete_requirement(bid_id: int, req_id: int):
    """Delete a requirement and its BidDocument links."""
    with get_dms_session() as session:
        req = _get_requirement_or_404(session, bid_id, req_id)
        title = req.title
        session.delete(req)
        return {"success": True, "deleted": title}


@router.post("/{bid_id}/requirements/from-category", dependencies=[require_role("editor")])
async def create_from_category(bid_id: int, data: CategoryRequest):
    """Bulk create requirements from all doc_types in a category."""
    with get_dms_session() as session:
        _get_bid_or_404(session, bid_id)

        doc_types = session.query(DocType).filter(DocType.category == data.category).all()
        if not doc_types:
            raise HTTPException(status_code=404, detail=f"No doc types found for category '{data.category}'")

        # Get existing requirement doc_type_ids for this bid
        existing_dt_ids = {
            r.doc_type_id for r in
            session.query(BidRequirement).filter(BidRequirement.bid_project_id == bid_id).all()
            if r.doc_type_id is not None
        }

        created = []
        skipped = 0
        for i, dt in enumerate(doc_types):
            if dt.id in existing_dt_ids:
                skipped += 1
                continue
            req = BidRequirement(
                bid_project_id=bid_id,
                doc_type_id=dt.id,
                title=dt.name,
                description=dt.description,
                sort_order=i,
            )
            session.add(req)
            session.flush()
            created.append(req.to_dict())

        return {"created": created, "skipped": skipped, "total": len(created)}


# ============================================================
# Document Linking
# ============================================================

@router.post("/{bid_id}/requirements/{req_id}/documents", dependencies=[require_role("editor")])
async def link_document(bid_id: int, req_id: int, data: LinkDocumentRequest, request: Request):
    """Link a DMS document to a requirement."""
    with get_dms_session() as session:
        _get_requirement_or_404(session, bid_id, req_id)

        doc = session.query(DmsDocument).filter(DmsDocument.id == data.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            bd = BidDocument(
                bid_requirement_id=req_id,
                document_id=data.document_id,
                status="linked",
                linked_by=get_current_user_id(request),
                notes=data.notes,
            )
            session.add(bd)
            session.flush()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Document already linked to this requirement")

        return bd.to_dict()


@router.delete("/{bid_id}/requirements/{req_id}/documents/{doc_id}", dependencies=[require_role("editor")])
async def unlink_document(bid_id: int, req_id: int, doc_id: int):
    """Unlink a document from a requirement."""
    with get_dms_session() as session:
        _get_requirement_or_404(session, bid_id, req_id)

        bd = session.query(BidDocument).filter(
            BidDocument.bid_requirement_id == req_id,
            BidDocument.document_id == doc_id,
        ).first()
        if not bd:
            raise HTTPException(status_code=404, detail="Document link not found")

        session.delete(bd)
        return {"success": True}


@router.patch("/{bid_id}/requirements/{req_id}/documents/{doc_id}", dependencies=[require_role("editor")])
async def update_bid_document(bid_id: int, req_id: int, doc_id: int, data: UpdateBidDocStatus):
    """Update BidDocument status (e.g., to 'verified')."""
    with get_dms_session() as session:
        _get_requirement_or_404(session, bid_id, req_id)

        bd = session.query(BidDocument).filter(
            BidDocument.bid_requirement_id == req_id,
            BidDocument.document_id == doc_id,
        ).first()
        if not bd:
            raise HTTPException(status_code=404, detail="Document link not found")

        if data.status not in ("linked", "verified"):
            raise HTTPException(status_code=400, detail="Status must be 'linked' or 'verified'")

        bd.status = data.status
        session.flush()
        return bd.to_dict()


# ============================================================
# Auto-match & Checklist
# ============================================================

@router.get("/{bid_id}/requirements/{req_id}/suggestions")
async def suggest_documents(bid_id: int, req_id: int):
    """Auto-match DMS documents by doc_type_id."""
    with get_dms_session() as session:
        req = _get_requirement_or_404(session, bid_id, req_id)

        if not req.doc_type_id:
            return {"suggestions": []}

        # Find active/draft documents with matching doc_type
        docs = session.query(DmsDocument).filter(
            DmsDocument.doc_type_id == req.doc_type_id,
            DmsDocument.status.in_(["active", "draft"]),
        ).order_by(DmsDocument.updated_at.desc()).limit(20).all()

        # Exclude already-linked documents
        linked_ids = {bd.document_id for bd in req.bid_documents}

        suggestions = []
        for doc in docs:
            if doc.id in linked_ids:
                continue
            suggestions.append({
                "id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "doc_type": {"id": doc.doc_type.id, "name": doc.doc_type.name, "code": doc.doc_type.code} if doc.doc_type else None,
                "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            })

        return {"suggestions": suggestions}


@router.get("/{bid_id}/checklist")
async def get_checklist(bid_id: int):
    """Readiness summary with per-requirement detail."""
    with get_dms_session() as session:
        _get_bid_or_404(session, bid_id)

        reqs = session.query(BidRequirement).filter(
            BidRequirement.bid_project_id == bid_id
        ).order_by(BidRequirement.sort_order, BidRequirement.id).all()

        items = []
        total = len(reqs)
        fulfilled = 0

        for req in reqs:
            item = {
                "id": req.id,
                "title": req.title,
                "is_required": req.is_required,
                "doc_type": {"id": req.doc_type.id, "name": req.doc_type.name} if req.doc_type else None,
                "linked_documents": [],
                "status": "missing",
            }

            for bd in req.bid_documents:
                doc = session.query(DmsDocument).filter(DmsDocument.id == bd.document_id).first()
                doc_info = {
                    "document_id": bd.document_id,
                    "document_title": doc.title if doc else None,
                    "link_status": bd.status,
                    "document_exists": doc is not None,
                }
                item["linked_documents"].append(doc_info)
                if doc is not None:
                    item["status"] = "fulfilled"

            if item["status"] == "fulfilled":
                fulfilled += 1

            items.append(item)

        missing = total - fulfilled
        percentage = round(fulfilled / total * 100) if total > 0 else 0

        return {
            "bid_project_id": bid_id,
            "total": total,
            "fulfilled": fulfilled,
            "missing": missing,
            "percentage": percentage,
            "items": items,
        }

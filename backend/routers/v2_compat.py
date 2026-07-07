"""
Legacy compatibility shim for BidSmart material search API.
Translates queries against new DMS models into old MaterialResponse format.
"""

import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, Query

from dms_models import (
    get_dms_session, DmsDocument, Revision, DmsFile,
    DocumentEntity, Entity, Folder,
)

logger = logging.getLogger("materialhub.routers.v2_compat")

router = APIRouter(prefix="/api/v2/compat", tags=["dms-compat"])


@router.get("/materials")
async def search_materials_compat(
    q: Optional[str] = Query(None),
    status: str = Query("valid"),
    company_id: Optional[int] = Query(None),
):
    """
    BidSmart-compatible material search endpoint.
    Returns results in the legacy MaterialResponse format.
    """
    with get_dms_session() as session:
        query = session.query(DmsDocument)

        # Status filter
        today = date.today()
        if status == "valid":
            query = query.filter(
                (DmsDocument.expiry_date.is_(None)) | (DmsDocument.expiry_date >= today)
            )
            query = query.filter(DmsDocument.status.in_(["draft", "active"]))
        elif status == "expired":
            query = query.filter(
                (DmsDocument.status == "expired") |
                ((DmsDocument.expiry_date.isnot(None)) & (DmsDocument.expiry_date < today))
            )

        # Company filter via entity links
        if company_id is not None:
            query = query.join(DocumentEntity).filter(
                DocumentEntity.entity_id == company_id,
            )

        # Keyword search
        if q:
            query = query.filter(DmsDocument.title.ilike(f"%{q}%"))

        docs = query.order_by(DmsDocument.updated_at.desc()).limit(200).all()

        results = []
        for doc in docs:
            cur_rev = doc.current_revision()
            if not cur_rev:
                continue

            # Get first file (original) from current revision
            files = [f for f in cur_rev.files if f.file_type == "original"]
            file_obj = files[0] if files else None

            # Get linked company entity
            owner_link = None
            for el in doc.entity_links:
                if el.role == "owner" and el.entity and el.entity.entity_type == "org":
                    owner_link = el
                    break

            result = {
                "id": doc.id,
                "document_id": doc.id,
                "company_id": owner_link.entity_id if owner_link else None,
                "person_id": None,
                "source_filename": None,
                "section": doc.folder.name if doc.folder else "",
                "title": doc.title,
                "heading_level": 1,
                "image_filename": file_obj.filename if file_obj else "",
                "image_url": f"/api/v2/files/{file_obj.id}" if file_obj else "",
                "file_size": file_obj.file_size if file_obj else 0,
                "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
                "is_expired": doc.expiry_date < today if doc.expiry_date else None,
                "material_type": doc.doc_type.code if doc.doc_type else None,
                "ocr_text": None,
                "extracted_data": None,
                "ocr_status": None,
                "ocr_error": None,
                "ocr_processed_at": None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            results.append(result)

        return {"results": results}

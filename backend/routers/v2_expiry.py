"""DMS Expiry Monitoring API endpoints."""

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, case

from dms_models import get_dms_session, DmsDocument, DocType
from dms_auth import get_accessible_folder_ids

logger = logging.getLogger("materialhub.routers.v2_expiry")

router = APIRouter(prefix="/api/v2/expiry", tags=["dms-expiry"])


def _doc_to_expiry_result(doc: DmsDocument) -> dict:
    """Format a document for expiry result lists."""
    return {
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "doc_type": {"id": doc.doc_type.id, "name": doc.doc_type.name, "code": doc.doc_type.code} if doc.doc_type else None,
        "folder": {"id": doc.folder.id, "name": doc.folder.name} if doc.folder else None,
        "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
        "days_until_expiry": (doc.expiry_date - date.today()).days if doc.expiry_date else None,
        "entity_names": [
            link.entity.name for link in doc.entity_links
            if link.entity and link.entity.name
        ],
    }


@router.get("/summary")
async def expiry_summary(request: Request):
    """Return aggregated expiry counts and per-DocType breakdown."""
    allowed_folders = get_accessible_folder_ids(request)
    today = date.today()
    d30 = today + timedelta(days=30)
    d60 = today + timedelta(days=60)
    d90 = today + timedelta(days=90)

    with get_dms_session() as session:
        # Base: active documents with expiry_date set
        base = session.query(DmsDocument).filter(
            DmsDocument.status == "active",
            DmsDocument.expiry_date.isnot(None),
        )
        if allowed_folders is not None:
            if not allowed_folders:
                return {"expiring_30d": 0, "expiring_60d": 0, "expiring_90d": 0, "expired": 0, "by_doc_type": []}
            base = base.filter(DmsDocument.folder_id.in_(allowed_folders))

        expiring_30d = base.filter(DmsDocument.expiry_date >= today, DmsDocument.expiry_date <= d30).count()
        expiring_60d = base.filter(DmsDocument.expiry_date >= today, DmsDocument.expiry_date <= d60).count()
        expiring_90d = base.filter(DmsDocument.expiry_date >= today, DmsDocument.expiry_date <= d90).count()
        expired = base.filter(DmsDocument.expiry_date < today).count()

        # Per DocType breakdown
        by_doc_type = []
        dt_rows = (
            session.query(
                DocType.id, DocType.name, DocType.code,
                func.count(DmsDocument.id).label("total"),
                func.sum(
                    case(
                        (DmsDocument.expiry_date < today, 1),
                        else_=0,
                    )
                ).label("expired_count"),
                func.sum(
                    case(
                        ((DmsDocument.expiry_date >= today) & (DmsDocument.expiry_date <= d30), 1),
                        else_=0,
                    )
                ).label("expiring_30d_count"),
            )
            .join(DmsDocument, DmsDocument.doc_type_id == DocType.id)
            .filter(
                DmsDocument.status == "active",
                DmsDocument.expiry_date.isnot(None),
                *([DmsDocument.folder_id.in_(allowed_folders)] if allowed_folders is not None else []),
            )
            .group_by(DocType.id)
            .all()
        )

        for row in dt_rows:
            by_doc_type.append({
                "doc_type_id": row[0],
                "doc_type_name": row[1],
                "doc_type_code": row[2],
                "total_with_expiry": row[3],
                "expired": row[4] or 0,
                "expiring_30d": row[5] or 0,
            })

        return {
            "expiring_30d": expiring_30d,
            "expiring_60d": expiring_60d,
            "expiring_90d": expiring_90d,
            "expired": expired,
            "by_doc_type": by_doc_type,
        }


@router.get("/expiring")
async def list_expiring(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List documents expiring within N days, ordered by soonest first."""
    allowed_folders = get_accessible_folder_ids(request)
    today = date.today()
    cutoff = today + timedelta(days=days)

    with get_dms_session() as session:
        query = session.query(DmsDocument).filter(
            DmsDocument.status.in_(["active", "draft"]),
            DmsDocument.expiry_date.isnot(None),
            DmsDocument.expiry_date >= today,
            DmsDocument.expiry_date <= cutoff,
        )
        if allowed_folders is not None:
            if not allowed_folders:
                return {"results": [], "total": 0, "days": days, "limit": limit, "offset": offset}
            query = query.filter(DmsDocument.folder_id.in_(allowed_folders))

        total = query.count()
        docs = query.order_by(DmsDocument.expiry_date.asc()).offset(offset).limit(limit).all()

        return {
            "results": [_doc_to_expiry_result(doc) for doc in docs],
            "total": total,
            "days": days,
            "limit": limit,
            "offset": offset,
        }


@router.get("/expired")
async def list_expired(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List active documents with past expiry_date (not yet archived)."""
    allowed_folders = get_accessible_folder_ids(request)
    today = date.today()

    with get_dms_session() as session:
        query = session.query(DmsDocument).filter(
            DmsDocument.status == "active",
            DmsDocument.expiry_date.isnot(None),
            DmsDocument.expiry_date < today,
        )
        if allowed_folders is not None:
            if not allowed_folders:
                return {"results": [], "total": 0, "limit": limit, "offset": offset}
            query = query.filter(DmsDocument.folder_id.in_(allowed_folders))

        total = query.count()
        docs = query.order_by(DmsDocument.expiry_date.asc()).offset(offset).limit(limit).all()

        return {
            "results": [_doc_to_expiry_result(doc) for doc in docs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("/update-status")
async def update_expired_status():
    """Batch transition active documents with past expiry_date to 'expired' status."""
    today = date.today()

    with get_dms_session() as session:
        docs = session.query(DmsDocument).filter(
            DmsDocument.status == "active",
            DmsDocument.expiry_date.isnot(None),
            DmsDocument.expiry_date < today,
        ).all()

        count = 0
        for doc in docs:
            doc.status = "expired"
            count += 1

    logger.info(f"Updated {count} expired documents to 'expired' status")
    return {"updated_count": count}

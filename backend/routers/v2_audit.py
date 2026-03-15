"""DMS Audit Log API endpoints."""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from dms_models import get_dms_session, AuditLog

logger = logging.getLogger("materialhub.routers.v2_audit")

router = APIRouter(prefix="/api/v2/audit", tags=["dms-audit"])


@router.get("/logs")
async def query_audit_logs(
    document_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Query audit log entries with optional filters."""
    with get_dms_session() as session:
        query = session.query(AuditLog)

        if document_id is not None:
            query = query.filter(
                AuditLog.target_type == "document",
                AuditLog.target_id == document_id,
            )

        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)

        if action:
            query = query.filter(AuditLog.action == action)

        if target_type:
            query = query.filter(AuditLog.target_type == target_type)

        if date_from:
            try:
                d = date.fromisoformat(date_from)
                query = query.filter(AuditLog.created_at >= d.isoformat())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date_from format")

        if date_to:
            try:
                d = date.fromisoformat(date_to)
                # Include the entire day
                query = query.filter(AuditLog.created_at < f"{d.isoformat()}T23:59:59.999999")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date_to format")

        total = query.count()
        logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

        import json
        results = []
        for log in logs:
            details = None
            if log.details:
                try:
                    details = json.loads(log.details)
                except (json.JSONDecodeError, TypeError):
                    details = log.details
            results.append({
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "target_title": log.target_title,
                "details": details,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            })

        return {"results": results, "total": total, "limit": limit, "offset": offset}

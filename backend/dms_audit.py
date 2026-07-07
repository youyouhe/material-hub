"""Audit logging helper for DMS operations."""

import json
import logging
from datetime import datetime

from dms_models import AuditLog

logger = logging.getLogger("materialhub.dms_audit")


def log_audit(
    session,
    user_id: int,
    action: str,
    target_type: str,
    target_id: int = None,
    target_title: str = None,
    details: dict = None,
    ip_address: str = None,
):
    """Record an audit log entry within the current session transaction.

    Args:
        session: SQLAlchemy session (must be within an active transaction)
        user_id: ID of the user performing the action
        action: One of create/update/delete/status_change/download/approve/reject/lock/unlock
        target_type: One of document/folder/entity/tag
        target_id: ID of the target object
        target_title: Human-readable title of the target
        details: Optional dict with change details (before/after, etc.)
        ip_address: Client IP address
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_title=target_title,
        details=json.dumps(details, ensure_ascii=False) if details else None,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    session.add(entry)

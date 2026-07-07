"""
DMS v2 Authentication API routes.
Uses DmsUser / DmsSession models; dual-writes to legacy sessions
for backward compatibility during migration.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from dms_models import get_dms_session, DmsUser, DmsSession

logger = logging.getLogger("materialhub.routers.v2_auth")

router = APIRouter(prefix="/api/v2/auth", tags=["authentication-v2"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict
    expires_at: str


class LogoutResponse(BaseModel):
    success: bool


class CheckResponse(BaseModel):
    valid: bool
    user: dict = None


# ============================================================
# Internal helpers
# ============================================================

def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


def _create_dms_session(dms_db, user_id: int) -> DmsSession:
    """Create a new DMS session token."""
    session_hours = int(os.getenv("AUTH_SESSION_HOURS", "24"))
    token = uuid.uuid4().hex
    expires_at = datetime.utcnow() + timedelta(hours=session_hours)

    dms_session = DmsSession(
        user_id=user_id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
    )
    dms_db.add(dms_session)
    dms_db.flush()
    return dms_session


def _create_legacy_session(user_id: int, token: str, expires_at: datetime):
    """Dual-write: also create a session in the legacy sessions table
    so the existing auth middleware continues to work."""
    try:
        from database import get_session, SessionToken
        with get_session() as legacy_db:
            legacy_session = SessionToken(
                user_id=user_id,
                token=token,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
            )
            legacy_db.add(legacy_session)
            legacy_db.commit()
    except Exception as e:
        logger.warning("Failed to dual-write legacy session: %s", e)


def _delete_legacy_session(token: str):
    """Remove a legacy session during logout."""
    try:
        from database import get_session, SessionToken
        with get_session() as legacy_db:
            legacy_db.query(SessionToken).filter(
                SessionToken.token == token
            ).delete()
            legacy_db.commit()
    except Exception as e:
        logger.warning("Failed to delete legacy session: %s", e)


def _validate_dms_session(token: str) -> Optional[dict]:
    """Validate a DMS session token. Returns user dict or None."""
    with get_dms_session() as dms_db:
        session = dms_db.query(DmsSession).filter(
            DmsSession.token == token
        ).first()
        if not session:
            return None
        if session.expires_at < datetime.utcnow():
            dms_db.delete(session)
            dms_db.flush()
            return None
        user = session.user
        user.last_login = datetime.utcnow()
        dms_db.flush()
        # Return dict to avoid DetachedInstanceError after session close
        return user.to_dict()


# ============================================================
# Endpoints
# ============================================================

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Authenticate with DmsUser and create DmsSession (dual-write to legacy)."""
    with get_dms_session() as dms_db:
        user = dms_db.query(DmsUser).filter(
            DmsUser.username == request.username
        ).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        if not _verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        session = _create_dms_session(dms_db, user.id)
        dms_db.commit()

        # Dual-write to legacy sessions table
        _create_legacy_session(user.legacy_user_id or user.id, session.token, session.expires_at)

        return LoginResponse(
            token=session.token,
            user=user.to_dict(),
            expires_at=session.expires_at.isoformat(),
        )


@router.post("/logout", response_model=LogoutResponse)
def logout(authorization: Optional[str] = Header(None)):
    """Logout by deleting DmsSession + legacy session."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")

    deleted = False
    with get_dms_session() as dms_db:
        session = dms_db.query(DmsSession).filter(
            DmsSession.token == token
        ).first()
        if session:
            dms_db.delete(session)
            dms_db.flush()
            deleted = True

    # Also delete from legacy sessions
    _delete_legacy_session(token)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return LogoutResponse(success=True)


@router.get("/check", response_model=CheckResponse)
def check(authorization: Optional[str] = Header(None)):
    """Check if a DMS session token is valid (falls back to legacy check)."""
    if not authorization or not authorization.startswith("Bearer "):
        return CheckResponse(valid=False)

    token = authorization.replace("Bearer ", "")

    # Try DMS session first
    user = _validate_dms_session(token)
    if user:
        return CheckResponse(valid=True, user=user)

    # Fall back to legacy session validation
    try:
        from database import get_session
        from auth import validate_session
        with get_session() as legacy_db:
            legacy_user = validate_session(legacy_db, token)
            if legacy_user:
                return CheckResponse(valid=True, user=legacy_user.to_dict())
    except Exception:
        pass

    return CheckResponse(valid=False)

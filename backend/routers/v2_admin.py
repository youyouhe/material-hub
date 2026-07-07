"""Admin user management API endpoints (DMS v2)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dms_models import get_dms_session, DmsUser, UserFolderAccess, Folder
from dms_auth import require_role, get_current_user_id
import bcrypt

logger = logging.getLogger("materialhub.routers.v2_admin")

router = APIRouter(prefix="/api/v2/admin", tags=["admin"])

VALID_ROLES = {"admin", "editor", "viewer"}


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


# ============================================================
# Internal: shadow legacy User for backward compatibility
# ============================================================

def _create_legacy_user_shadow(dms_user_id: int, username: str, role: str, password_hash: str):
    """Create a shadow legacy User so UserFolderAccess (keyed by legacy user ID)
    and other legacy references continue to work during transition."""
    try:
        from database import get_session, User
        from datetime import datetime
        with get_session() as legacy_db:
            legacy = User(
                username=username,
                password_hash=password_hash,
                role=role,
                created_at=datetime.utcnow(),
            )
            legacy_db.add(legacy)
            legacy_db.commit()
            legacy_db.refresh(legacy)
            legacy_id = legacy.id

        # Link back in a separate DMS session
        with get_dms_session() as dms_db:
            u = dms_db.query(DmsUser).filter(DmsUser.id == dms_user_id).first()
            if u:
                u.legacy_user_id = legacy_id
                dms_db.commit()
        return legacy_id
    except Exception as e:
        logger.warning("Failed to create legacy shadow user: %s", e)
        return None


def _update_legacy_user_shadow(legacy_user_id: int, updates: dict):
    """Sync changes to the shadow legacy User."""
    if not legacy_user_id:
        return
    try:
        from database import get_session, User
        with get_session() as legacy_db:
            legacy = legacy_db.query(User).filter(
                User.id == legacy_user_id
            ).first()
            if legacy:
                for key, value in updates.items():
                    if hasattr(legacy, key):
                        setattr(legacy, key, value)
                legacy_db.commit()
    except Exception as e:
        logger.warning("Failed to update legacy shadow user: %s", e)


# ============================================================
# Request schemas
# ============================================================

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "editor"


class ChangeRoleRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    new_password: str


# ============================================================
# Endpoints
# ============================================================

@router.get("/users", dependencies=[require_role("admin")])
async def list_users():
    """List all users with roles and folder access."""
    with get_dms_session() as dms_db:
        users = dms_db.query(DmsUser).order_by(DmsUser.id).all()
        user_list = [u.to_dict() for u in users]

        all_access = dms_db.query(UserFolderAccess).all()
        access_map: dict[int, list[int]] = {}
        for a in all_access:
            access_map.setdefault(a.user_id, []).append(a.folder_id)

    # Map folder access by legacy_user_id (which UserFolderAccess references)
    for u in user_list:
        lookup_id = u.get("legacy_user_id") or u["id"]
        u["folder_ids"] = access_map.get(lookup_id, [])

    return {"users": user_list}


@router.post("/users", dependencies=[require_role("admin")])
async def create_user(data: CreateUserRequest):
    """Create a new user with username, password, and role."""
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    password_hash = _hash_password(data.password)

    with get_dms_session() as dms_db:
        existing = dms_db.query(DmsUser).filter(DmsUser.username == data.username).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"User '{data.username}' already exists")

        user = DmsUser(
            username=data.username,
            password_hash=password_hash,
            role=data.role,
        )
        dms_db.add(user)
        dms_db.flush()
        dms_db.refresh(user)
        user_dict = user.to_dict()

    # Create shadow legacy user AFTER DMS session commits (avoid SQLite lock)
    _create_legacy_user_shadow(user_dict["id"], data.username, data.role, password_hash)

    # Re-fetch to get updated legacy_user_id
    with get_dms_session() as dms_db:
        updated = dms_db.query(DmsUser).filter(DmsUser.id == user_dict["id"]).first()
        return updated.to_dict() if updated else user_dict


@router.put("/users/{user_id}/role", dependencies=[require_role("admin")])
async def change_role(user_id: int, data: ChangeRoleRequest, request: Request):
    """Change a user's role. Admins cannot demote themselves."""
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    current_user_id = get_current_user_id(request)

    with get_dms_session() as dms_db:
        user = dms_db.query(DmsUser).filter(DmsUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_id == current_user_id and data.role != "admin":
            raise HTTPException(status_code=400, detail="Cannot demote yourself")

        user.role = data.role
        legacy_id = user.legacy_user_id
        dms_db.flush()
        _update_legacy_user_shadow(legacy_id, {"role": data.role})
        return user.to_dict()


@router.put("/users/{user_id}/password", dependencies=[require_role("admin")])
async def reset_password(user_id: int, data: ResetPasswordRequest):
    """Reset a user's password."""
    if len(data.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    with get_dms_session() as dms_db:
        user = dms_db.query(DmsUser).filter(DmsUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        new_hash = _hash_password(data.new_password)
        user.password_hash = new_hash
        dms_db.flush()
        _update_legacy_user_shadow(user, {"password_hash": new_hash})
        return {"success": True, "username": user.username}


# ============================================================
# Folder Access Management
# ============================================================

class SetFolderAccessRequest(BaseModel):
    folder_ids: list[int]


@router.get("/users/{user_id}/folders", dependencies=[require_role("admin")])
async def get_user_folders(user_id: int):
    """Get the list of folder IDs a user has been granted access to."""
    # user_id here is DmsUser.id; resolve to the access-table key
    with get_dms_session() as dms_db:
        user = dms_db.query(DmsUser).filter(DmsUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # UserFolderAccess uses legacy_user_id (or DmsUser.id for new users)
        lookup_id = user.legacy_user_id or user.id
        rows = dms_db.query(UserFolderAccess).filter(
            UserFolderAccess.user_id == lookup_id
        ).all()
        return {"folder_ids": [r.folder_id for r in rows]}


@router.put("/users/{user_id}/folders", dependencies=[require_role("admin")])
async def set_user_folders(user_id: int, data: SetFolderAccessRequest):
    """Replace the full set of folder access for a user.

    Pass an empty list to revoke all access.
    """
    with get_dms_session() as dms_db:
        user = dms_db.query(DmsUser).filter(DmsUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate folder IDs
        if data.folder_ids:
            valid = dms_db.query(Folder.id).filter(Folder.id.in_(data.folder_ids)).all()
            valid_ids = {r[0] for r in valid}
            invalid = set(data.folder_ids) - valid_ids
            if invalid:
                raise HTTPException(status_code=400, detail=f"Invalid folder IDs: {sorted(invalid)}")

        # UserFolderAccess uses legacy_user_id (or DmsUser.id for new users)
        lookup_id = user.legacy_user_id or user.id

        # Delete existing access
        dms_db.query(UserFolderAccess).filter(
            UserFolderAccess.user_id == lookup_id
        ).delete()

        # Insert new access
        for fid in set(data.folder_ids):
            dms_db.add(UserFolderAccess(user_id=lookup_id, folder_id=fid))

        dms_db.flush()
        return {"success": True, "folder_ids": sorted(set(data.folder_ids))}

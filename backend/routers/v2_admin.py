"""Admin user management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from database import get_session, User
from auth import hash_password
from dms_auth import require_role, get_current_user_id
from dms_models import get_dms_session, UserFolderAccess, Folder

logger = logging.getLogger("materialhub.routers.v2_admin")

router = APIRouter(prefix="/api/v2/admin", tags=["admin"])

VALID_ROLES = {"admin", "editor", "viewer"}


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
    with get_session() as session:
        users = session.query(User).order_by(User.id).all()
        user_list = [u.to_dict() for u in users]

    # Attach folder access info
    with get_dms_session() as dms_session:
        all_access = dms_session.query(UserFolderAccess).all()
        access_map: dict[int, list[int]] = {}
        for a in all_access:
            access_map.setdefault(a.user_id, []).append(a.folder_id)

    for u in user_list:
        u["folder_ids"] = access_map.get(u["id"], [])

    return {"users": user_list}


@router.post("/users", dependencies=[require_role("admin")])
async def create_user(data: CreateUserRequest):
    """Create a new user with username, password, and role."""
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    with get_session() as session:
        existing = session.query(User).filter(User.username == data.username).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"User '{data.username}' already exists")

        user = User(
            username=data.username,
            password_hash=hash_password(data.password),
            role=data.role,
        )
        session.add(user)
        session.flush()
        return user.to_dict()


@router.put("/users/{user_id}/role", dependencies=[require_role("admin")])
async def change_role(user_id: int, data: ChangeRoleRequest, request: Request):
    """Change a user's role. Admins cannot demote themselves."""
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    current_user_id = get_current_user_id(request)

    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_id == current_user_id and data.role != "admin":
            raise HTTPException(status_code=400, detail="Cannot demote yourself")

        user.role = data.role
        session.flush()
        return user.to_dict()


@router.put("/users/{user_id}/password", dependencies=[require_role("admin")])
async def reset_password(user_id: int, data: ResetPasswordRequest):
    """Reset a user's password."""
    if len(data.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.password_hash = hash_password(data.new_password)
        session.flush()
        return {"success": True, "username": user.username}


# ============================================================
# Folder Access Management
# ============================================================

class SetFolderAccessRequest(BaseModel):
    folder_ids: list[int]


@router.get("/users/{user_id}/folders", dependencies=[require_role("admin")])
async def get_user_folders(user_id: int):
    """Get the list of folder IDs a user has been granted access to."""
    with get_dms_session() as session:
        rows = session.query(UserFolderAccess).filter(
            UserFolderAccess.user_id == user_id
        ).all()
        return {"folder_ids": [r.folder_id for r in rows]}


@router.put("/users/{user_id}/folders", dependencies=[require_role("admin")])
async def set_user_folders(user_id: int, data: SetFolderAccessRequest):
    """Replace the full set of folder access for a user.

    Pass an empty list to revoke all access.
    """
    # Validate user exists
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    with get_dms_session() as session:
        # Validate folder IDs
        if data.folder_ids:
            valid = session.query(Folder.id).filter(Folder.id.in_(data.folder_ids)).all()
            valid_ids = {r[0] for r in valid}
            invalid = set(data.folder_ids) - valid_ids
            if invalid:
                raise HTTPException(status_code=400, detail=f"Invalid folder IDs: {sorted(invalid)}")

        # Delete existing access
        session.query(UserFolderAccess).filter(
            UserFolderAccess.user_id == user_id
        ).delete()

        # Insert new access
        for fid in set(data.folder_ids):
            session.add(UserFolderAccess(user_id=user_id, folder_id=fid))

        session.flush()
        return {"success": True, "folder_ids": sorted(set(data.folder_ids))}

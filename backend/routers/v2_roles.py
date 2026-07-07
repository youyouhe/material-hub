"""RBAC roles & folder-level permission management."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dms_models import (
    get_dms_session, DmsRole, DmsRoleFolderPermission, DmsUserRole,
    DmsUser, Folder,
)
from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_roles")
router = APIRouter(prefix="/api/v2/admin/roles", tags=["admin-roles"])

VALID_PERMISSIONS = {"read", "write", "admin"}


# ============================================================
# Schemas
# ============================================================

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class FolderPermissionSet(BaseModel):
    folder_ids: list[int]
    permission: str = "read"  # read | write | admin


class UserRoleAssign(BaseModel):
    user_id: int
    role_id: int


# ============================================================
# Role CRUD
# ============================================================

@router.get("/", dependencies=[require_role("admin")])
async def list_roles():
    """List all roles with folder permission counts."""
    with get_dms_session() as s:
        roles = s.query(DmsRole).order_by(DmsRole.id).all()
        result = []
        for r in roles:
            d = r.to_dict()
            d["folder_count"] = s.query(DmsRoleFolderPermission).filter(
                DmsRoleFolderPermission.role_id == r.id
            ).count()
            d["user_count"] = s.query(DmsUserRole).filter(
                DmsUserRole.role_id == r.id
            ).count()
            result.append(d)
        return {"roles": result}


@router.post("/", dependencies=[require_role("admin")])
async def create_role(data: RoleCreate):
    """Create a new custom role."""
    with get_dms_session() as s:
        if s.query(DmsRole).filter(DmsRole.name == data.name).first():
            raise HTTPException(status_code=409, detail=f"Role '{data.name}' already exists")
        role = DmsRole(name=data.name, description=data.description)
        s.add(role)
        s.flush()
        return role.to_dict()


@router.patch("/{role_id}", dependencies=[require_role("admin")])
async def update_role(role_id: int, data: RoleUpdate):
    """Update role name or description. System roles cannot be renamed."""
    with get_dms_session() as s:
        role = s.query(DmsRole).filter(DmsRole.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if data.name and data.name != role.name and role.is_system:
            raise HTTPException(status_code=400, detail="Cannot rename system roles")
        if data.name:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        s.flush()
        return role.to_dict()


@router.delete("/{role_id}", dependencies=[require_role("admin")])
async def delete_role(role_id: int):
    """Delete a role. System roles cannot be deleted."""
    with get_dms_session() as s:
        role = s.query(DmsRole).filter(DmsRole.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.is_system:
            raise HTTPException(status_code=400, detail="Cannot delete system roles")
        s.delete(role)
        return {"success": True}


# ============================================================
# Folder Permissions
# ============================================================

@router.get("/{role_id}/folders", dependencies=[require_role("admin")])
async def get_role_folders(role_id: int):
    """Get all folder permissions for a role."""
    with get_dms_session() as s:
        role = s.query(DmsRole).filter(DmsRole.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        perms = s.query(DmsRoleFolderPermission).filter(
            DmsRoleFolderPermission.role_id == role_id
        ).all()
        return {"folder_permissions": [p.to_dict() for p in perms]}


@router.get("/{role_id}/folders/{folder_id}", dependencies=[require_role("admin")])
async def get_role_folder_permission(role_id: int, folder_id: int):
    """Get a role's permission on a specific folder."""
    with get_dms_session() as s:
        perm = s.query(DmsRoleFolderPermission).filter(
            DmsRoleFolderPermission.role_id == role_id,
            DmsRoleFolderPermission.folder_id == folder_id,
        ).first()
        return {"permission": perm.permission if perm else None}


@router.put("/{role_id}/folders", dependencies=[require_role("admin")])
async def set_role_folders(role_id: int, data: FolderPermissionSet):
    """Batch-set folder permissions for a role. Replaces ALL existing permissions."""
    if data.permission not in VALID_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {data.permission}")

    with get_dms_session() as s:
        role = s.query(DmsRole).filter(DmsRole.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        # Delete existing
        s.query(DmsRoleFolderPermission).filter(
            DmsRoleFolderPermission.role_id == role_id
        ).delete()

        # Insert new
        for fid in set(data.folder_ids):
            s.add(DmsRoleFolderPermission(
                role_id=role_id, folder_id=fid, permission=data.permission
            ))
        s.flush()

        # Sync to agents bound to this role
        from dms_models import ApiAgent, AgentFolderAccess
        agents = s.query(ApiAgent).filter(
            ApiAgent.role == role.name, ApiAgent.is_active == True
        ).all()
        for agent in agents:
            s.query(AgentFolderAccess).filter(AgentFolderAccess.agent_id == agent.id).delete()
            for fid in set(data.folder_ids):
                s.add(AgentFolderAccess(agent_id=agent.id, folder_id=fid))
        if agents:
            logger.info(f"Synced folder permissions to {len(agents)} agent(s) of role '{role.name}'")

        return {"success": True, "count": len(data.folder_ids), "agents_synced": len(agents)}


@router.put("/{role_id}/folders/{folder_id}", dependencies=[require_role("admin")])
async def set_role_folder_permission(role_id: int, folder_id: int, permission: str = "read"):
    """Set a role's permission on a single folder."""
    if permission not in VALID_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")

    with get_dms_session() as s:
        role = s.query(DmsRole).filter(DmsRole.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        existing = s.query(DmsRoleFolderPermission).filter(
            DmsRoleFolderPermission.role_id == role_id,
            DmsRoleFolderPermission.folder_id == folder_id,
        ).first()
        if existing:
            existing.permission = permission
        else:
            s.add(DmsRoleFolderPermission(
                role_id=role_id, folder_id=folder_id, permission=permission
            ))

        # Sync to agents bound to this role
        from dms_models import ApiAgent, AgentFolderAccess
        agents = s.query(ApiAgent).filter(
            ApiAgent.role == role.name, ApiAgent.is_active == True
        ).all()
        for agent in agents:
            af = s.query(AgentFolderAccess).filter(
                AgentFolderAccess.agent_id == agent.id,
                AgentFolderAccess.folder_id == folder_id,
            ).first()
            if af:
                af.folder_id = folder_id  # keep existing record, permission is folder-level
            else:
                s.add(AgentFolderAccess(agent_id=agent.id, folder_id=folder_id))

        return {"success": True, "agents_synced": len(agents)}


# ============================================================
# User-Role Assignment
# ============================================================

@router.get("/users/{user_id}", dependencies=[require_role("admin")])
async def get_user_roles(user_id: int):
    """Get all roles assigned to a user."""
    with get_dms_session() as s:
        assignments = s.query(DmsUserRole).filter(
            DmsUserRole.user_id == user_id
        ).all()
        return {"roles": [a.to_dict() for a in assignments]}


@router.post("/users/assign", dependencies=[require_role("admin")])
async def assign_user_role(data: UserRoleAssign):
    """Assign a role to a user."""
    with get_dms_session() as s:
        if not s.query(DmsUser).filter(DmsUser.id == data.user_id).first():
            raise HTTPException(status_code=404, detail="User not found")
        if not s.query(DmsRole).filter(DmsRole.id == data.role_id).first():
            raise HTTPException(status_code=404, detail="Role not found")
        if s.query(DmsUserRole).filter(
            DmsUserRole.user_id == data.user_id,
            DmsUserRole.role_id == data.role_id,
        ).first():
            raise HTTPException(status_code=409, detail="User already has this role")
        s.add(DmsUserRole(user_id=data.user_id, role_id=data.role_id))
        return {"success": True}


@router.delete("/users/{user_id}/roles/{role_id}", dependencies=[require_role("admin")])
async def remove_user_role(user_id: int, role_id: int):
    """Remove a role from a user."""
    with get_dms_session() as s:
        s.query(DmsUserRole).filter(
            DmsUserRole.user_id == user_id,
            DmsUserRole.role_id == role_id,
        ).delete()
        return {"success": True}


# ============================================================
# Effective Permissions (for current user)
# ============================================================

@router.post("/sync-agents", dependencies=[require_role("admin")])
async def sync_all_agents():
    """Sync folder permissions from roles to agents. Call after changing role permissions."""
    from dms_models import ApiAgent, AgentFolderAccess, DmsRoleFolderPermission
    with get_dms_session() as s:
        agents = s.query(ApiAgent).filter(ApiAgent.is_active == True).all()
        synced = 0
        for agent in agents:
            role = s.query(DmsRole).filter(DmsRole.name == agent.role).first()
            if not role:
                continue
            perms = s.query(DmsRoleFolderPermission).filter(
                DmsRoleFolderPermission.role_id == role.id
            ).all()
            # Replace agent folder access
            s.query(AgentFolderAccess).filter(AgentFolderAccess.agent_id == agent.id).delete()
            for p in perms:
                s.add(AgentFolderAccess(agent_id=agent.id, folder_id=p.folder_id))
            synced += 1
        return {"synced": synced}


@router.get("/me/effective")
async def get_my_permissions(request: Request):
    """Get the current user's effective folder permissions."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with get_dms_session() as s:
        # Admin has everything
        user = s.query(DmsUser).filter(DmsUser.id == user_id).first()
        if user and user.role == "admin":
            return {"is_admin": True, "folders": []}

        # Collect permissions from all assigned roles
        role_ids = [
            r[0] for r in s.query(DmsUserRole.role_id).filter(
                DmsUserRole.user_id == user_id
            ).all()
        ]
        if not role_ids:
            return {"is_admin": False, "folders": []}

        perms = s.query(DmsRoleFolderPermission).filter(
            DmsRoleFolderPermission.role_id.in_(role_ids)
        ).all()

        # Merge: highest permission wins per folder
        perm_order = {"read": 0, "write": 1, "admin": 2}
        folder_perms: dict[int, str] = {}
        for p in perms:
            current = folder_perms.get(p.folder_id, "read")
            if perm_order.get(p.permission, 0) > perm_order.get(current, 0):
                folder_perms[p.folder_id] = p.permission

        return {
            "is_admin": False,
            "folders": [
                {"folder_id": fid, "permission": perm}
                for fid, perm in folder_perms.items()
            ],
        }

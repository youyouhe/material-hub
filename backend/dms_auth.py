"""RBAC permission checking for DMS v2 endpoints.

Supports two modes:
1. New: DmsUserRole → DmsRole → DmsRoleFolderPermission (role-based)
2. Legacy: DmsUser.role field + UserFolderAccess (user-based, fallback)
"""

from fastapi import Request, HTTPException, Depends

from dms_models import (
    get_dms_session, UserFolderAccess, AgentFolderAccess, Folder,
    DmsUser, DmsRole, DmsRoleFolderPermission, DmsUserRole,
)

ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "admin": 2}
PERMISSION_LEVEL = {"read": 0, "write": 1, "admin": 2}


def get_current_user_id(request: Request) -> int:
    """Extract current user ID from request state (set by auth middleware)."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def get_current_user_role(request: Request) -> str:
    """Extract current user role from request state."""
    return getattr(request.state, "user_role", "editor")


def require_role(min_role: str):
    """FastAPI dependency: requires at least the specified global role level."""
    min_level = ROLE_HIERARCHY.get(min_role, 0)

    async def checker(request: Request):
        user_role = getattr(request.state, "user_role", None)
        if not user_role or ROLE_HIERARCHY.get(user_role, -1) < min_level:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    return Depends(checker)


def _expand_folder_ids(session, assigned_ids: list[int]) -> list[int]:
    """Expand a list of folder IDs to include all sub-folders."""
    if not assigned_ids:
        return []
    assigned_folders = session.query(Folder).filter(Folder.id.in_(assigned_ids)).all()
    assigned_paths = [f.path for f in assigned_folders]

    all_folder_ids = set(assigned_ids)
    for path in assigned_paths:
        children = session.query(Folder.id).filter(
            Folder.path.like(f"{path}%"),
            Folder.id.notin_(assigned_ids),
        ).all()
        for row in children:
            all_folder_ids.add(row[0])
    return list(all_folder_ids)


def _get_role_based_folder_ids(user_id: int) -> dict[int, str] | None:
    """Get folder→permission mapping from role assignments.
    Returns None for admin (unrestricted), or dict of folder_id→max_permission.
    """
    with get_dms_session() as s:
        user = s.query(DmsUser).filter(DmsUser.id == user_id).first()
        if not user:
            return {}

        # Legacy admin check (DmsUser.role field)
        if user.role == "admin":
            return None

        # Get role assignments
        role_ids = [
            r[0] for r in s.query(DmsUserRole.role_id).filter(
                DmsUserRole.user_id == user_id
            ).all()
        ]

        # If user has admin role → unrestricted
        if role_ids:
            admin_role = s.query(DmsRole).filter(
                DmsRole.id.in_(role_ids), DmsRole.name == "admin"
            ).first()
            if admin_role:
                return None

        # Collect permissions from all roles
        folder_perms: dict[int, str] = {}
        if role_ids:
            perms = s.query(DmsRoleFolderPermission).filter(
                DmsRoleFolderPermission.role_id.in_(role_ids)
            ).all()
            for p in perms:
                current = folder_perms.get(p.folder_id, "read")
                if PERMISSION_LEVEL.get(p.permission, 0) > PERMISSION_LEVEL.get(current, 0):
                    folder_perms[p.folder_id] = p.permission

        # If no role-based permissions, fall back to legacy UserFolderAccess
        if not folder_perms:
            legacy = s.query(UserFolderAccess.folder_id).filter(
                UserFolderAccess.user_id == user_id
            ).all()
            for row in legacy:
                folder_perms[row[0]] = "write"  # Legacy access = full write

        return folder_perms if folder_perms else {}


def get_accessible_folder_ids(request: Request) -> list[int] | None:
    """Return list of folder IDs the current user/agent can access, or None if unrestricted.

    - Admin role: returns None (no restriction)
    - Agent: checks AgentFolderAccess table
    - User: checks DmsUserRole → DmsRole → DmsRoleFolderPermission
            falls back to legacy UserFolderAccess
    - If no folders assigned, returns [] (sees nothing).
    """
    user_role = getattr(request.state, "user_role", "editor")
    if user_role == "admin":
        return None  # No restriction

    # Agent request
    agent_id = getattr(request.state, "agent_id", None)
    if agent_id is not None:
        with get_dms_session() as session:
            assigned = session.query(AgentFolderAccess.folder_id).filter(
                AgentFolderAccess.agent_id == agent_id
            ).all()
            assigned_ids = [row[0] for row in assigned]
            return _expand_folder_ids(session, assigned_ids)

    # User request — role-based permissions
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return []

    perms = _get_role_based_folder_ids(user_id)
    if perms is None:
        return None  # Admin — unrestricted
    if not perms:
        return []   # No access

    with get_dms_session() as session:
        return _expand_folder_ids(session, list(perms.keys()))


def get_folder_permission(request: Request, folder_id: int) -> str:
    """Get the current user's effective permission on a specific folder.
    Returns 'admin', 'write', 'read', or 'none'.
    """
    user_role = getattr(request.state, "user_role", "editor")
    if user_role == "admin":
        return "admin"

    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return "none"

    perms = _get_role_based_folder_ids(user_id)
    if perms is None:
        return "admin"
    if not perms:
        return "none"

    # Check direct match + parent folders
    with get_dms_session() as s:
        folder = s.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            return perms.get(folder_id, "none")

        # Walk up the folder tree
        current = folder
        while current:
            p = perms.get(current.id)
            if p:
                return p
            if current.parent_id:
                current = s.query(Folder).filter(Folder.id == current.parent_id).first()
            else:
                break

    return "none"


def require_folder_permission(min_permission: str):
    """FastAPI dependency: requires at least the specified permission on the target folder.
    Extracts folder_id from path parameter.

    Usage:
        @router.post("/folders/{folder_id}/documents", dependencies=[require_folder_permission("write")])
    """
    min_level = PERMISSION_LEVEL.get(min_permission, 0)

    async def checker(request: Request):
        # Try to extract folder_id from path
        folder_id = None
        path_parts = request.url.path.rstrip("/").split("/")
        for i, part in enumerate(path_parts):
            if part == "folders" and i + 1 < len(path_parts):
                try:
                    folder_id = int(path_parts[i + 1])
                except ValueError:
                    pass
                break

        if folder_id is None:
            return  # Can't determine folder — let the endpoint handle

        user_perm = get_folder_permission(request, folder_id)
        if PERMISSION_LEVEL.get(user_perm, -1) < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Requires '{min_permission}' permission on folder {folder_id}"
            )
    return Depends(checker)

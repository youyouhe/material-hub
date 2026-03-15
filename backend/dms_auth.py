"""RBAC permission checking for DMS v2 endpoints."""

from fastapi import Request, HTTPException, Depends

from dms_models import get_dms_session, UserFolderAccess, AgentFolderAccess, Folder

ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "admin": 2}


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
    """FastAPI dependency that checks the current user has at least the specified role.

    Usage:
        @router.post("/", dependencies=[require_role("editor")])
        async def create_something(...):
    """
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


def get_accessible_folder_ids(request: Request) -> list[int] | None:
    """Return list of folder IDs the current user/agent can access, or None if unrestricted.

    - Admin role: returns None (no restriction)
    - Agent: checks AgentFolderAccess table
    - User: checks UserFolderAccess table
    - If no folders assigned, returns empty list (sees nothing).
    """
    user_role = getattr(request.state, "user_role", "editor")
    if user_role == "admin":
        return None  # No restriction

    # Check if this is an agent request
    agent_id = getattr(request.state, "agent_id", None)
    if agent_id is not None:
        with get_dms_session() as session:
            assigned = session.query(AgentFolderAccess.folder_id).filter(
                AgentFolderAccess.agent_id == agent_id
            ).all()
            assigned_ids = [row[0] for row in assigned]
            return _expand_folder_ids(session, assigned_ids)

    # Regular user
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return []

    with get_dms_session() as session:
        assigned = session.query(UserFolderAccess.folder_id).filter(
            UserFolderAccess.user_id == user_id
        ).all()
        assigned_ids = [row[0] for row in assigned]
        return _expand_folder_ids(session, assigned_ids)

"""DMS Bid Project API endpoints."""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from dms_models import (
    get_dms_session, BidProject, BidRequirement, BidDocument,
    BidTeamMember, Folder, Entity, DmsDocument,
    recompute_subtree_paths, VALID_BID_TRANSITIONS,
)
from dms_auth import require_role, get_current_user_id
from dms_audit import log_audit

logger = logging.getLogger("materialhub.routers.v2_bids")

router = APIRouter(prefix="/api/v2/bids", tags=["dms-bids"])


# ============================================================
# Request schemas
# ============================================================

class BidProjectCreate(BaseModel):
    name: str
    bid_number: Optional[str] = None
    buyer: Optional[str] = None
    budget: Optional[str] = None
    deadline: Optional[str] = None  # ISO date string
    description: Optional[str] = None


class BidProjectUpdate(BaseModel):
    name: Optional[str] = None
    bid_number: Optional[str] = None
    buyer: Optional[str] = None
    budget: Optional[str] = None
    deadline: Optional[str] = None
    description: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str
    result: Optional[str] = None  # reason for won/lost/cancelled


class TeamMemberCreate(BaseModel):
    entity_id: int
    role: str


# ============================================================
# Helpers
# ============================================================

def _requirement_summary(session, bid_project_id: int) -> dict:
    """Get requirement fulfillment counts for a bid project."""
    reqs = session.query(BidRequirement).filter(
        BidRequirement.bid_project_id == bid_project_id
    ).all()
    total = len(reqs)
    fulfilled = 0
    for req in reqs:
        # Fulfilled if at least one linked/verified BidDocument exists
        # and the underlying DmsDocument still exists
        for bd in req.bid_documents:
            doc = session.query(DmsDocument).filter(DmsDocument.id == bd.document_id).first()
            if doc:
                fulfilled += 1
                break
    missing = total - fulfilled
    return {"total": total, "fulfilled": fulfilled, "missing": missing}


def _auto_create_folder(session, project_name: str) -> Optional[int]:
    """Create a folder under /投标文件/进行中/ for a new bid project."""
    # Find the "进行中" folder
    active_folder = session.query(Folder).filter(
        Folder.name == "进行中",
        Folder.parent_id.isnot(None),
    ).first()

    if not active_folder:
        # Try to find parent "投标文件" and create "进行中" if missing
        bid_root = session.query(Folder).filter(Folder.name == "投标文件").first()
        if not bid_root:
            logger.warning("投标文件 root folder not found, skipping auto-folder creation")
            return None
        # Look for 进行中 under bid root
        active_folder = session.query(Folder).filter(
            Folder.name == "进行中",
            Folder.parent_id == bid_root.id,
        ).first()
        if not active_folder:
            logger.warning("投标文件/进行中 folder not found, skipping auto-folder creation")
            return None

    # Create project subfolder
    import re
    slug = project_name.strip().lower()
    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-') or 'untitled'

    folder = Folder(
        name=project_name,
        parent_id=active_folder.id,
        path=f"{active_folder.path}{slug}/",
    )
    session.add(folder)
    session.flush()
    return folder.id


def _move_folder_to_archive(session, folder_id: int):
    """Move a bid project folder from 进行中 to 已归档."""
    if not folder_id:
        return

    folder = session.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        return

    # Find the 已归档 folder (sibling of 进行中 under 投标文件)
    bid_root = session.query(Folder).filter(Folder.name == "投标文件").first()
    if not bid_root:
        return

    archive_folder = session.query(Folder).filter(
        Folder.name == "已归档",
        Folder.parent_id == bid_root.id,
    ).first()
    if not archive_folder:
        return

    folder.parent_id = archive_folder.id
    folder.parent = archive_folder
    recompute_subtree_paths(session, folder)


# ============================================================
# Endpoints
# ============================================================

@router.post("/", dependencies=[require_role("editor")])
async def create_bid_project(data: BidProjectCreate, request: Request):
    """Create a new bid project with auto-folder creation."""
    with get_dms_session() as session:
        deadline_date = None
        if data.deadline:
            try:
                deadline_date = date.fromisoformat(data.deadline)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid deadline format, use YYYY-MM-DD")

        user_id = get_current_user_id(request)

        # Auto-create folder
        folder_id = _auto_create_folder(session, data.name)

        project = BidProject(
            name=data.name,
            bid_number=data.bid_number,
            buyer=data.buyer,
            folder_id=folder_id,
            budget=data.budget,
            deadline=deadline_date,
            description=data.description,
            created_by=user_id,
        )
        session.add(project)
        session.flush()

        log_audit(session, user_id, "create", "bid_project", project.id, project.name,
                  ip_address=request.client.host if request.client else None)

        return project.to_dict()


@router.get("/")
async def list_bid_projects(
    status: Optional[str] = Query(None),
    buyer: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List bid projects with optional filters."""
    with get_dms_session() as session:
        query = session.query(BidProject)

        if status:
            query = query.filter(BidProject.status == status)
        if buyer:
            query = query.filter(BidProject.buyer.ilike(f"%{buyer}%"))
        if q:
            query = query.filter(BidProject.name.ilike(f"%{q}%"))

        total = query.count()
        projects = query.order_by(BidProject.created_at.desc()).offset(offset).limit(limit).all()

        results = []
        for p in projects:
            d = p.to_dict()
            d["requirements_summary"] = _requirement_summary(session, p.id)
            results.append(d)

        return {"results": results, "total": total, "limit": limit, "offset": offset}


@router.get("/{bid_id}")
async def get_bid_project(bid_id: int):
    """Get bid project detail with team and requirement summary."""
    with get_dms_session() as session:
        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Bid project not found")

        result = project.to_dict()
        result["team_members"] = [tm.to_dict() for tm in project.team_members]
        result["requirements_summary"] = _requirement_summary(session, project.id)
        return result


@router.patch("/{bid_id}", dependencies=[require_role("editor")])
async def update_bid_project(bid_id: int, data: BidProjectUpdate, request: Request):
    """Update bid project fields."""
    with get_dms_session() as session:
        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Bid project not found")

        update_data = data.model_dump(exclude_unset=True)

        if "deadline" in update_data:
            val = update_data.pop("deadline")
            if val:
                try:
                    project.deadline = date.fromisoformat(val)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid deadline format")
            else:
                project.deadline = None

        for field, value in update_data.items():
            setattr(project, field, value)

        session.flush()

        user_id = get_current_user_id(request)
        log_audit(session, user_id, "update", "bid_project", project.id, project.name,
                  ip_address=request.client.host if request.client else None)

        return project.to_dict()


@router.patch("/{bid_id}/status", dependencies=[require_role("editor")])
async def update_bid_status(bid_id: int, data: StatusUpdate, request: Request):
    """Transition bid project status."""
    with get_dms_session() as session:
        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Bid project not found")

        if not project.can_transition_to(data.status):
            allowed = VALID_BID_TRANSITIONS.get(project.status, set())
            raise HTTPException(
                status_code=409,
                detail=f"Cannot transition from '{project.status}' to '{data.status}'. "
                       f"Allowed: {', '.join(allowed) if allowed else 'none (terminal state)'}",
            )

        old_status = project.status
        project.status = data.status
        if data.result:
            project.result = data.result

        # Move folder to archive on terminal status
        if data.status in ("won", "lost", "cancelled"):
            _move_folder_to_archive(session, project.folder_id)

        session.flush()

        user_id = get_current_user_id(request)
        log_audit(session, user_id, "status_change", "bid_project", project.id, project.name,
                  details={"old_status": old_status, "new_status": data.status, "result": data.result},
                  ip_address=request.client.host if request.client else None)

        return project.to_dict()


@router.delete("/{bid_id}", dependencies=[require_role("editor")])
async def delete_bid_project(bid_id: int, request: Request):
    """Delete bid project with cascade. Does NOT delete linked DMS documents."""
    with get_dms_session() as session:
        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Bid project not found")

        name = project.name
        user_id = get_current_user_id(request)
        log_audit(session, user_id, "delete", "bid_project", bid_id, name,
                  ip_address=request.client.host if request.client else None)

        session.delete(project)
        return {"success": True, "deleted": name}


# ============================================================
# Team Member Endpoints
# ============================================================

@router.post("/{bid_id}/team", dependencies=[require_role("editor")])
async def add_team_member(bid_id: int, data: TeamMemberCreate, request: Request):
    """Add a team member to a bid project."""
    with get_dms_session() as session:
        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Bid project not found")

        entity = session.query(Entity).filter(Entity.id == data.entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        try:
            member = BidTeamMember(
                bid_project_id=bid_id,
                entity_id=data.entity_id,
                role=data.role,
            )
            session.add(member)
            session.flush()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Team member with this entity and role already exists")

        user_id = get_current_user_id(request)
        log_audit(session, user_id, "update", "bid_project", bid_id, project.name,
                  details={"action": "add_team_member", "entity_id": data.entity_id, "role": data.role},
                  ip_address=request.client.host if request.client else None)

        return member.to_dict()


@router.get("/{bid_id}/team")
async def list_team_members(bid_id: int):
    """List team members with entity details."""
    with get_dms_session() as session:
        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Bid project not found")

        return {"team_members": [tm.to_dict() for tm in project.team_members]}


@router.delete("/{bid_id}/team/{member_id}", dependencies=[require_role("editor")])
async def remove_team_member(bid_id: int, member_id: int, request: Request):
    """Remove a team member from a bid project."""
    with get_dms_session() as session:
        member = session.query(BidTeamMember).filter(
            BidTeamMember.id == member_id,
            BidTeamMember.bid_project_id == bid_id,
        ).first()
        if not member:
            raise HTTPException(status_code=404, detail="Team member not found")

        project = session.query(BidProject).filter(BidProject.id == bid_id).first()
        user_id = get_current_user_id(request)
        log_audit(session, user_id, "update", "bid_project", bid_id,
                  project.name if project else None,
                  details={"action": "remove_team_member", "entity_id": member.entity_id, "role": member.role},
                  ip_address=request.client.host if request.client else None)

        session.delete(member)
        return {"success": True}

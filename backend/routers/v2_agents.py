"""API Agent management endpoints for MCP / external integrations."""

import secrets
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dms_auth import require_role
from dms_models import get_dms_session, ApiAgent, AgentFolderAccess, Folder

logger = logging.getLogger("materialhub.routers.v2_agents")

router = APIRouter(prefix="/api/v2/admin/agents", tags=["admin-agents"])


# ============================================================
# Request schemas
# ============================================================

class CreateAgentRequest(BaseModel):
    name: str
    role: str = "viewer"
    description: Optional[str] = None
    folder_ids: list[int] = []


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SetAgentFoldersRequest(BaseModel):
    folder_ids: list[int]


VALID_ROLES = {"admin", "editor", "viewer"}


def _generate_token() -> str:
    """Generate a secure agent token with mh-agent- prefix."""
    return f"mh-agent-{secrets.token_hex(24)}"


# ============================================================
# Endpoints
# ============================================================

@router.get("/", dependencies=[require_role("admin")])
async def list_agents():
    """List all API agents."""
    with get_dms_session() as session:
        agents = session.query(ApiAgent).order_by(ApiAgent.id).all()
        return {"agents": [a.to_safe_dict() for a in agents]}


@router.post("/", dependencies=[require_role("admin")])
async def create_agent(data: CreateAgentRequest):
    """Create a new API agent and return the generated token."""
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    token = _generate_token()

    with get_dms_session() as session:
        agent = ApiAgent(
            name=data.name,
            token=token,
            role=data.role,
            description=data.description,
        )
        session.add(agent)
        session.flush()

        # Set folder access
        if data.folder_ids and data.role != "admin":
            valid = session.query(Folder.id).filter(Folder.id.in_(data.folder_ids)).all()
            valid_ids = {r[0] for r in valid}
            for fid in set(data.folder_ids) & valid_ids:
                session.add(AgentFolderAccess(agent_id=agent.id, folder_id=fid))
            session.flush()

        # Return full token only on creation
        result = agent.to_dict()
        logger.info(f"Created API agent: {agent.name} (id={agent.id})")
        return result


@router.get("/{agent_id}", dependencies=[require_role("admin")])
async def get_agent(agent_id: int):
    """Get agent details (token preview only)."""
    with get_dms_session() as session:
        agent = session.query(ApiAgent).filter(ApiAgent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent.to_safe_dict()


@router.put("/{agent_id}", dependencies=[require_role("admin")])
async def update_agent(agent_id: int, data: UpdateAgentRequest):
    """Update agent name, role, description, or active status."""
    with get_dms_session() as session:
        agent = session.query(ApiAgent).filter(ApiAgent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if data.name is not None:
            agent.name = data.name
        if data.role is not None:
            if data.role not in VALID_ROLES:
                raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
            agent.role = data.role
        if data.description is not None:
            agent.description = data.description
        if data.is_active is not None:
            agent.is_active = data.is_active

        session.flush()
        return agent.to_safe_dict()


@router.delete("/{agent_id}", dependencies=[require_role("admin")])
async def delete_agent(agent_id: int):
    """Delete an API agent."""
    with get_dms_session() as session:
        agent = session.query(ApiAgent).filter(ApiAgent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        name = agent.name
        session.delete(agent)
        session.flush()
        logger.info(f"Deleted API agent: {name} (id={agent_id})")
        return {"success": True}


@router.post("/{agent_id}/regenerate-token", dependencies=[require_role("admin")])
async def regenerate_token(agent_id: int):
    """Regenerate the token for an agent. Returns the new full token."""
    with get_dms_session() as session:
        agent = session.query(ApiAgent).filter(ApiAgent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent.token = _generate_token()
        session.flush()
        logger.info(f"Regenerated token for agent: {agent.name} (id={agent_id})")
        return {"token": agent.token}


@router.put("/{agent_id}/folders", dependencies=[require_role("admin")])
async def set_agent_folders(agent_id: int, data: SetAgentFoldersRequest):
    """Replace the full set of folder access for an agent."""
    with get_dms_session() as session:
        agent = session.query(ApiAgent).filter(ApiAgent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Validate folder IDs
        if data.folder_ids:
            valid = session.query(Folder.id).filter(Folder.id.in_(data.folder_ids)).all()
            valid_ids = {r[0] for r in valid}
            invalid = set(data.folder_ids) - valid_ids
            if invalid:
                raise HTTPException(status_code=400, detail=f"Invalid folder IDs: {sorted(invalid)}")

        # Delete existing access
        session.query(AgentFolderAccess).filter(
            AgentFolderAccess.agent_id == agent_id
        ).delete()

        # Insert new access
        for fid in set(data.folder_ids):
            session.add(AgentFolderAccess(agent_id=agent_id, folder_id=fid))

        session.flush()
        return {"success": True, "folder_ids": sorted(set(data.folder_ids))}

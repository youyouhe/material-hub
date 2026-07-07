"""DMS Tag API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from dms_models import get_dms_session, Tag, DocumentTag
from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_tags")

router = APIRouter(prefix="/api/v2/tags", tags=["dms-tags"])


class TagCreate(BaseModel):
    name: str
    color: Optional[str] = None


@router.get("/")
async def list_tags():
    """List all tags with document count for each."""
    with get_dms_session() as session:
        tags = session.query(Tag).order_by(Tag.name).all()

        results = []
        for t in tags:
            d = t.to_dict()
            d["document_count"] = session.query(DocumentTag).filter(
                DocumentTag.tag_id == t.id
            ).count()
            results.append(d)

        return {"tags": results, "total": len(results)}


@router.post("/", dependencies=[require_role("editor")])
async def create_tag(data: TagCreate):
    """Create a new tag."""
    with get_dms_session() as session:
        existing = session.query(Tag).filter(Tag.name == data.name).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Tag '{data.name}' already exists")

        tag = Tag(name=data.name, color=data.color)
        session.add(tag)
        session.flush()
        return tag.to_dict()


@router.delete("/{tag_id}", dependencies=[require_role("editor")])
async def delete_tag(tag_id: int):
    """Delete a tag and all its document associations."""
    with get_dms_session() as session:
        tag = session.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")

        name = tag.name
        session.delete(tag)  # Cascade handles DocumentTag
        return {"success": True, "deleted": name}

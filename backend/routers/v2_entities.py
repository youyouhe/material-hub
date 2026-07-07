"""DMS Entity (Organization / Person) API endpoints."""

import json
import logging
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dms_models import get_dms_session, Entity, DocumentEntity, EntityRelation
from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_entities")

router = APIRouter(prefix="/api/v2/entities", tags=["dms-entities"])


class EntityCreate(BaseModel):
    entity_type: str  # org/person
    name: str
    attributes: Optional[Any] = None
    parent_id: Optional[int] = None


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    attributes: Optional[Any] = None
    parent_id: Optional[int] = None


@router.get("/")
async def list_entities(
    type: Optional[str] = Query(None, alias="type"),
    parent_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
):
    """List entities with optional type and parent filters."""
    with get_dms_session() as session:
        query = session.query(Entity)

        if type:
            query = query.filter(Entity.entity_type == type)

        if parent_id is not None:
            query = query.filter(Entity.parent_id == parent_id)

        if q:
            query = query.filter(Entity.name.ilike(f"%{q}%"))

        entities = query.order_by(Entity.name).all()

        results = []
        for e in entities:
            d = e.to_dict()
            d["document_count"] = session.query(DocumentEntity).filter(
                DocumentEntity.entity_id == e.id
            ).count()
            results.append(d)

        return {"results": results, "total": len(results)}


@router.post("/", dependencies=[require_role("editor")])
async def create_entity(data: EntityCreate):
    """Create a new entity."""
    if not data.entity_type or not data.entity_type.strip():
        raise HTTPException(status_code=400, detail="entity_type is required")

    with get_dms_session() as session:
        if data.parent_id:
            parent = session.query(Entity).filter(Entity.id == data.parent_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent entity not found")

        attrs_str = json.dumps(data.attributes, ensure_ascii=False) if data.attributes else None

        entity = Entity(
            entity_type=data.entity_type,
            name=data.name,
            attributes=attrs_str,
            parent_id=data.parent_id,
        )
        session.add(entity)
        session.flush()
        return entity.to_dict()


@router.get("/{entity_id}")
async def get_entity(entity_id: int):
    """Get entity detail with document count and children summary."""
    with get_dms_session() as session:
        entity = session.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        result = entity.to_dict()
        result["document_count"] = session.query(DocumentEntity).filter(
            DocumentEntity.entity_id == entity_id
        ).count()

        # Children summary
        children = session.query(Entity).filter(Entity.parent_id == entity_id).all()
        result["children"] = [{"id": c.id, "name": c.name, "entity_type": c.entity_type} for c in children]

        # Relations (both directions)
        outgoing = session.query(EntityRelation).filter(
            EntityRelation.from_id == entity_id
        ).all()
        incoming = session.query(EntityRelation).filter(
            EntityRelation.to_id == entity_id
        ).all()
        result["relations"] = {
            "outgoing": [r.to_dict() for r in outgoing],
            "incoming": [r.to_dict() for r in incoming],
        }

        return result


@router.patch("/{entity_id}", dependencies=[require_role("editor")])
async def update_entity(entity_id: int, data: EntityUpdate):
    """Update entity fields."""
    with get_dms_session() as session:
        entity = session.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        update_data = data.model_dump(exclude_unset=True)

        if "attributes" in update_data:
            val = update_data.pop("attributes")
            entity.attributes = json.dumps(val, ensure_ascii=False) if val is not None else None

        if "parent_id" in update_data:
            new_parent_id = update_data.pop("parent_id")
            if new_parent_id == entity_id:
                raise HTTPException(status_code=400, detail="Cannot set entity as its own parent")
            if new_parent_id:
                parent = session.query(Entity).filter(Entity.id == new_parent_id).first()
                if not parent:
                    raise HTTPException(status_code=404, detail="Parent entity not found")
            entity.parent_id = new_parent_id

        for field, value in update_data.items():
            setattr(entity, field, value)

        session.flush()
        return entity.to_dict()


@router.delete("/{entity_id}", dependencies=[require_role("editor")])
async def delete_entity(entity_id: int):
    """Delete entity (must have no linked documents)."""
    with get_dms_session() as session:
        entity = session.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        link_count = session.query(DocumentEntity).filter(
            DocumentEntity.entity_id == entity_id
        ).count()
        if link_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Entity is linked to {link_count} document(s). Unlink them first."
            )

        name = entity.name
        session.delete(entity)
        return {"success": True, "deleted": name}

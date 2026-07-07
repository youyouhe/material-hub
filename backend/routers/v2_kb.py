"""Knowledge Base Search API Router (DMS v2)."""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from dms_auth import get_accessible_folder_ids
from kb_search import vector_search, hybrid_search
from kb_ingest import reingest_all_documents, get_kb_status
from kb_entity_sync import sync_entities_to_kb, sync_folders_to_kb
from kb_event_ingest import get_document_events, get_event_detail, search_events_by_entity
from kb_multihop import multihop_search

logger = logging.getLogger("materialhub.routers.v2_kb")

router = APIRouter(prefix="/api/v2/kb", tags=["kb-search"])


def _format_kb_result(r: dict) -> dict:
    """Format a KB search result for API response."""
    result = {
        "doc_id": r.get("doc_id"),
        "chunk_id": r.get("chunk_id"),
        "title": r.get("title", ""),
        "content": r.get("content", ""),
        "heading_path": r.get("heading_path"),
        "score": r.get("score") or r.get("rrf_score"),
        "doc_type": r.get("doc_type", ""),
        "folder": r.get("folder", ""),
        "entity_names": r.get("entity_names", []),
        "snippet": r.get("snippet"),
    }
    # Remove None values
    return {k: v for k, v in result.items() if v is not None}


@router.get("/search")
async def kb_search(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    mode: str = Query("hybrid", description="Search mode: vector | hybrid"),
    top_k: int = Query(20, ge=1, le=50, description="Max results"),
):
    """Semantic/vector search over document knowledge base.

    Modes:
    - vector: pure vector similarity search
    - hybrid: Reciprocal Rank Fusion of vector + FTS5 keyword results
    """
    allowed_folders = get_accessible_folder_ids(request)

    if mode == "vector":
        results = vector_search(
            query=q,
            top_k=top_k,
            allowed_folder_ids=allowed_folders,
        )
    else:
        results = hybrid_search(
            query=q,
            top_k=top_k,
            allowed_folder_ids=allowed_folders,
        )

    formatted = [_format_kb_result(r) for r in results]
    return {
        "results": formatted,
        "total": len(formatted),
        "mode": mode,
    }


@router.get("/search/multihop")
async def kb_multihop_search(
    request: Request,
    q: str = Query(..., min_length=1, description="Natural language question"),
    top_k: int = Query(10, ge=1, le=50),
    max_hops: int = Query(2, ge=1, le=3, description="Graph expansion depth"),
    explain: bool = Query(False, description="Include detailed search trace"),
):
    """Multi-hop knowledge graph search with entity-aware reasoning.

    Traverses entity relationships and events to find documents
    through indirect connections. Suitable for questions like:
    "Which certifications does the company that signed contract X hold?"
    """
    allowed_folders = get_accessible_folder_ids(request)
    result = multihop_search(
        query=q,
        top_k=top_k,
        max_hops=max_hops,
        allowed_folder_ids=allowed_folders,
    )

    response = {
        "results": result["results"],
        "total": result["total"],
    }
    if explain:
        response["trace"] = result.get("trace", {})

    return response


@router.post("/reindex")
async def kb_reindex(request: Request):
    """Rebuild all KB indexes for active documents (admin only).

    Processes: chunks → embeddings → vector index.
    Documents that already have KB indexes are re-indexed.
    """
    # Only admin can trigger reindex
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        return {
            "error": {
                "code": "FORBIDDEN",
                "message": "Only admin can trigger KB reindex"
            }
        }, 403

    result = reingest_all_documents()
    return {"reindex": result}


@router.get("/status")
async def kb_status():
    """Get KB index statistics."""
    return get_kb_status()


@router.post("/sync")
async def kb_sync(request: Request):
    """Sync entities and folders from SQLite to PostgreSQL KB.

    Triggered automatically on entity/folder CRUD, but can also
    be called manually to force a full sync.
    """
    from kb_entity_sync import sync_all_to_kb
    result = sync_all_to_kb()
    return {"sync": result}


@router.get("/events/{event_id}")
async def kb_event_detail(event_id: int):
    """Get event detail with linked entities and document info."""
    result = get_event_detail(event_id)
    if not result:
        return {"error": {"code": "EVENT_NOT_FOUND", "message": "Event not found"}}
    return {"event": result}


@router.get("/documents/{doc_id}/events")
async def kb_document_events(doc_id: int):
    """Get all extracted events for a document."""
    events = get_document_events(doc_id)
    return {"doc_id": doc_id, "events": events, "total": len(events)}


@router.get("/entities/search")
async def kb_entity_search(
    q: str = Query(..., min_length=1, description="Entity name to search"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search KB entities by name (from mirrored dms_entities)."""
    from kb_database import get_session_local
    from kb_models import KbEntity

    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        entities = session.query(KbEntity).filter(
            KbEntity.name.ilike(f"%{q}%")
        ).limit(limit).all()
        return {
            "entities": [e.to_dict() for e in entities],
            "total": len(entities),
        }
    finally:
        session.close()


@router.get("/entities/{entity_name}/graph")
async def kb_entity_graph(
    entity_name: str,
    depth: int = Query(1, ge=1, le=3, description="Exploration depth"),
):
    """Explore the knowledge graph around an entity.

    Returns: connected entities, shared events, and related documents.
    """
    # Find entity
    from kb_database import get_session_local
    from kb_models import KbEntity, KbEntityRelation, KbEventEntity, KbEvent

    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        entity = session.query(KbEntity).filter(
            KbEntity.name.ilike(f"%{entity_name}%")
        ).first()
        if not entity:
            return {"error": {"code": "ENTITY_NOT_FOUND", "message": "Entity not found"}}

        # Get relations (outgoing + incoming)
        outgoing = session.query(KbEntityRelation).filter(
            KbEntityRelation.from_entity_id == entity.id
        ).all()
        incoming = session.query(KbEntityRelation).filter(
            KbEntityRelation.to_entity_id == entity.id
        ).all()

        related_entity_ids = set()
        relations = []
        for r in outgoing + incoming:
            rid = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
            related_entity_ids.add(rid)
            relations.append({
                "from_id": r.from_entity_id,
                "to_id": r.to_entity_id,
                "relation": r.relation,
            })

        # Get related entities' names
        related_entities = session.query(KbEntity).filter(
            KbEntity.id.in_(related_entity_ids)
        ).all() if related_entity_ids else []

        # Get events linked to this entity
        event_links = session.query(KbEventEntity).filter(
            KbEventEntity.entity_id == entity.id
        ).limit(50).all()
        event_ids = [l.event_id for l in event_links]
        events = session.query(KbEvent).filter(KbEvent.id.in_(event_ids)).all() if event_ids else []

        # Depth-2: find entities related to related entities
        depth2 = []
        if depth >= 2 and related_entity_ids:
            depth2_links = session.query(KbEntityRelation).filter(
                (KbEntityRelation.from_entity_id.in_(related_entity_ids))
                | (KbEntityRelation.to_entity_id.in_(related_entity_ids))
            ).limit(50).all()
            depth2_ids = set()
            for r in depth2_links:
                depth2_ids.add(r.from_entity_id)
                depth2_ids.add(r.to_entity_id)
            depth2_ids -= {entity.id} | related_entity_ids
            depth2 = session.query(KbEntity).filter(
                KbEntity.id.in_(depth2_ids)
            ).limit(10).all()

        return {
            "entity": entity.to_dict(),
            "relations": relations,
            "related_entities": [e.to_dict() for e in related_entities],
            "events": [_event_summary(e) for e in events],
            "depth2_entities": [e.to_dict() for e in depth2] if depth >= 2 else [],
        }
    finally:
        session.close()


@router.get("/entities/relations/batch")
async def kb_batch_entity_relations(
    names: str = Query(..., description="Comma-separated entity names"),
):
    """Get relations among a set of entities by name.

    Returns edges between any two entities in the given set.
    Used by the knowledge graph panel to show entity-to-entity links.
    """
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not name_list:
        return {"relations": []}

    from kb_database import get_session_local
    from kb_models import KbEntity, KbEntityRelation

    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        # Find all entities matching the names
        entities = session.query(KbEntity).filter(
            KbEntity.name.in_(name_list)
        ).all()
        entity_map = {e.id: e for e in entities}

        if len(entity_map) < 2:
            return {"relations": []}

        eids = list(entity_map.keys())
        # Find relations where both ends are in our entity set
        relations = session.query(KbEntityRelation).filter(
            (KbEntityRelation.from_entity_id.in_(eids))
            & (KbEntityRelation.to_entity_id.in_(eids))
        ).all()

        result = []
        for r in relations:
            from_e = entity_map.get(r.from_entity_id)
            to_e = entity_map.get(r.to_entity_id)
            if from_e and to_e:
                result.append({
                    "from_name": from_e.name,
                    "from_type": from_e.entity_type,
                    "to_name": to_e.name,
                    "to_type": to_e.entity_type,
                    "relation": r.relation,
                })

        return {"relations": result}
    finally:
        session.close()


def _event_summary(event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "event_type": event.event_type,
    }

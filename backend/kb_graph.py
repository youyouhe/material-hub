"""
Knowledge Graph Expansion Engine.

BFS traversal of entity-relation-event graph for multi-hop reasoning.
Ported from SAG's expandEvents/graph traversal in search-service.ts.
"""

import logging
from typing import List, Dict, Set, Optional
from collections import deque

from kb_database import get_session_local
from kb_models import KbEntity, KbEntityRelation, KbEvent, KbEventEntity, KbChunk

logger = logging.getLogger("materialhub.kb_graph")


def expand_entity_graph(
    seed_entity_ids: List[int],
    max_depth: int = 2,
    source_entity_ids: Optional[List[int]] = None,
) -> Dict:
    """BFS traversal of entity relations from seed entities.

    Args:
        seed_entity_ids: starting entity IDs
        max_depth: max hops to traverse (1-3)
        source_entity_ids: optional filter to only include these entity IDs

    Returns:
        {
            entities: {id: {depth, relations_out, relations_in}}
            events: [{id, title, event_type, event_date, linked_entity_ids}]
            chunks: [{id, doc_id, content}]
        }
    """
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        visited_entities: Set[int] = set()
        visited_events: Set[int] = set()
        entity_depths: Dict[int, int] = {}
        all_relations = []
        all_events = []

        # BFS queue: (entity_id, depth)
        queue = deque()
        for eid in seed_entity_ids:
            queue.append((eid, 0))
            visited_entities.add(eid)
            entity_depths[eid] = 0

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Find outgoing relations (current → target)
            outgoing = session.query(KbEntityRelation).filter(
                KbEntityRelation.from_entity_id == current_id
            ).all()
            for rel in outgoing:
                all_relations.append({
                    "from_id": rel.from_entity_id,
                    "to_id": rel.to_entity_id,
                    "relation": rel.relation,
                    "depth": depth + 1,
                })
                if rel.to_entity_id not in visited_entities:
                    visited_entities.add(rel.to_entity_id)
                    entity_depths[rel.to_entity_id] = depth + 1
                    queue.append((rel.to_entity_id, depth + 1))

            # Find incoming relations (source → current)
            incoming = session.query(KbEntityRelation).filter(
                KbEntityRelation.to_entity_id == current_id
            ).all()
            for rel in incoming:
                all_relations.append({
                    "from_id": rel.from_entity_id,
                    "to_id": rel.to_entity_id,
                    "relation": rel.relation,
                    "depth": depth + 1,
                })
                if rel.from_entity_id not in visited_entities:
                    visited_entities.add(rel.from_entity_id)
                    entity_depths[rel.from_entity_id] = depth + 1
                    queue.append((rel.from_entity_id, depth + 1))

            # Find events linked to this entity
            event_links = session.query(KbEventEntity).filter(
                KbEventEntity.entity_id == current_id
            ).limit(50).all()
            for link in event_links:
                if link.event_id not in visited_events:
                    visited_events.add(link.event_id)

        # Load entity details
        entities_detail = {}
        if visited_entities:
            entity_rows = session.query(KbEntity).filter(
                KbEntity.id.in_(visited_entities)
            ).all()
            for e in entity_rows:
                entities_detail[e.id] = {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "depth": entity_depths.get(e.id, 0),
                }

        # Load events with their linked entities
        events_detail = []
        if visited_events:
            event_rows = session.query(KbEvent).filter(
                KbEvent.id.in_(visited_events)
            ).order_by(KbEvent.event_date.desc().nullslast()).limit(100).all()

            for evt in event_rows:
                # Get linked entity IDs for this event
                elinks = session.query(KbEventEntity).filter(
                    KbEventEntity.event_id == evt.id
                ).all()
                events_detail.append({
                    "id": evt.id,
                    "doc_id": evt.doc_id,
                    "title": evt.title,
                    "event_type": evt.event_type,
                    "event_date": evt.event_date.isoformat() if evt.event_date else None,
                    "description": evt.description,
                    "linked_entity_ids": [l.entity_id for l in elinks],
                })

        return {
            "entities": entities_detail,
            "relations": all_relations,
            "events": events_detail,
        }
    finally:
        session.close()


def get_chunks_for_entity(entity_id: int, limit: int = 20) -> List[Dict]:
    """Find document chunks associated with an entity through events."""
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        # Find events linked to this entity
        elinks = session.query(KbEventEntity).filter(
            KbEventEntity.entity_id == entity_id
        ).limit(limit).all()
        event_ids = [l.event_id for l in elinks]

        if not event_ids:
            return []

        # Find chunks from events' parent documents
        events = session.query(KbEvent).filter(
            KbEvent.id.in_(event_ids)
        ).all()
        doc_ids = list(set(e.doc_id for e in events))

        chunks = session.query(KbChunk).filter(
            KbChunk.doc_id.in_(doc_ids)
        ).order_by(KbChunk.chunk_index).limit(limit).all()

        return [
            {"id": c.id, "doc_id": c.doc_id, "content": c.content,
             "heading_path": c.heading_path, "chunk_index": c.chunk_index}
            for c in chunks
        ]
    finally:
        session.close()


def get_entity_neighborhood(entity_name: str, depth: int = 2) -> Dict:
    """Explore an entity's full neighborhood: relations, events, documents.

    Used by the MCP kb_get_entity_graph tool and API endpoint.
    """
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        entity = session.query(KbEntity).filter(
            KbEntity.name.ilike(f"%{entity_name}%")
        ).first()
        if not entity:
            return {"error": "Entity not found", "entity_name": entity_name}

        # 1. Get relations
        outgoing = session.query(KbEntityRelation).filter(
            KbEntityRelation.from_entity_id == entity.id
        ).all()
        incoming = session.query(KbEntityRelation).filter(
            KbEntityRelation.to_entity_id == entity.id
        ).all()

        related_ids = set()
        relations = []
        for r in outgoing:
            related_ids.add(r.to_entity_id)
            relations.append({"direction": "out", "target_id": r.to_entity_id, "relation": r.relation})
        for r in incoming:
            related_ids.add(r.from_entity_id)
            relations.append({"direction": "in", "source_id": r.from_entity_id, "relation": r.relation})

        related_entities = []
        if related_ids:
            related_entities = [
                {"id": e.id, "name": e.name, "type": e.entity_type}
                for e in session.query(KbEntity).filter(KbEntity.id.in_(related_ids)).all()
            ]

        # 2. Get linked events
        event_links = session.query(KbEventEntity).filter(
            KbEventEntity.entity_id == entity.id
        ).limit(30).all()
        event_ids = [l.event_id for l in event_links]

        events = []
        if event_ids:
            event_rows = session.query(KbEvent).filter(
                KbEvent.id.in_(event_ids)
            ).order_by(KbEvent.event_date.desc().nullslast()).all()
            events = [
                {"id": e.id, "title": e.title, "event_type": e.event_type,
                 "event_date": e.event_date.isoformat() if e.event_date else None,
                 "doc_id": e.doc_id}
                for e in event_rows
            ]

        # 3. Get document chunks
        doc_ids = list(set(e["doc_id"] for e in events))
        chunks = []
        if doc_ids:
            chunk_rows = session.query(KbChunk).filter(
                KbChunk.doc_id.in_(doc_ids[:5])
            ).order_by(KbChunk.chunk_index).limit(10).all()
            chunks = [{"id": c.id, "doc_id": c.doc_id, "preview": c.content[:100]} for c in chunk_rows]

        return {
            "entity": {"id": entity.id, "name": entity.name, "type": entity.entity_type},
            "relations": relations,
            "related_entities": related_entities,
            "events": events,
            "chunks": chunks,
        }
    finally:
        session.close()

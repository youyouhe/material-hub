"""
Knowledge Base Event Ingestion Pipeline.

Handles: extract events from KB chunks → deduplicate → embed → store data entity links.
Triggered after KB chunk ingestion completes.
"""

import logging
from datetime import date
from typing import List, Dict, Optional

from kb_database import get_session_local
from kb_models import KbEvent, KbEntity, KbEventEntity, KbChunkEvent
from kb_embedding import embed_text

logger = logging.getLogger("materialhub.kb_event_ingest")


def ingest_events_for_document(doc_id: int) -> int:
    """Extract events from document chunks and store in KB.

    Called after kb_ingest.ingest_document_chunks() succeeds.
    Runs asynchronously (non-blocking).

    Args:
        doc_id: SQLite dms_documents.id

    Returns:
        Number of events created
    """
    try:
        from kb_extraction import extract_events_from_document
        events = extract_events_from_document(doc_id)
    except Exception as e:
        logger.warning("Event extraction failed for doc %d: %s", doc_id, e)
        return 0

    if not events:
        logger.info("Document %d: no events extracted", doc_id)
        return 0

    SessionLocal = get_session_local()
    session = SessionLocal()
    created = 0

    try:
        # Remove existing events for this doc (re-extraction)
        old_events = session.query(KbEvent).filter(KbEvent.doc_id == doc_id).all()
        for old in old_events:
            session.query(KbEventEntity).filter(KbEventEntity.event_id == old.id).delete()
            session.query(KbChunkEvent).filter(KbChunkEvent.event_id == old.id).delete()
        session.query(KbEvent).filter(KbEvent.doc_id == doc_id).delete()

        for event_info in events:
            try:
                # Parse event date
                event_date = _parse_date(event_info.get("event_date"))

                # Create event
                desc = event_info.get("content") or event_info.get("summary", "")
                embedding = embed_text(f"{event_info['title']}\n\n{desc}")

                event = KbEvent(
                    doc_id=doc_id,
                    title=event_info["title"][:512],
                    description=desc[:2000],
                    event_date=event_date,
                    event_type=event_info.get("event_type", "other"),
                    embedding=embedding,
                    source_chunk_ids=event_info.get("source_chunk_ids", []),
                    attributes={
                        "keywords": event_info.get("keywords", []),
                        "summary": event_info.get("summary", ""),
                    },
                )
                session.add(event)
                session.flush()  # Get event.id

                # Link entities to event
                entity_names = [e["name"] for e in event_info.get("entities", [])]
                linked = _link_entities_to_event(session, event.id, entity_names, doc_id)
                created += 1

            except Exception as e:
                logger.warning("Failed to store event '%s': %s",
                               event_info.get("title", "?"), e)
                continue

        session.commit()
        logger.info("Document %d: %d events stored", doc_id, created)

    except Exception as e:
        session.rollback()
        logger.error("Event ingest transaction failed for doc %d: %s", doc_id, e)
    finally:
        session.close()

    return created


def _parse_date(value) -> Optional[date]:
    """Parse date from various formats."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%Y%m%d"]:
        try:
            from datetime import datetime
            dt = datetime.strptime(s[:10], fmt[:len(s[:10])])
            return dt.date()
        except ValueError:
            continue
    return None


def _link_entities_to_event(session, event_id: int, entity_names: List[str], doc_id: int) -> int:
    """Link KB entities to an event by name matching.

    Tries exact match first, then normalized (case-insensitive) match.
    Only links entities that already exist in kb_entities.

    Returns number of entities linked.
    """
    if not entity_names:
        return 0

    linked = 0
    for name in entity_names:
        name = name.strip()
        if len(name) < 2:
            continue

        # Exact match
        entity = session.query(KbEntity).filter(KbEntity.name == name).first()
        if not entity:
            # Case-insensitive match
            entity = session.query(KbEntity).filter(
                KbEntity.name.ilike(name)
            ).first()

        if entity:
            # Check for duplicate link
            existing = session.query(KbEventEntity).filter(
                KbEventEntity.event_id == event_id,
                KbEventEntity.entity_id == entity.id,
            ).first()
            if not existing:
                link = KbEventEntity(
                    event_id=event_id,
                    entity_id=entity.id,
                    role="subject",
                )
                session.add(link)
                linked += 1

    return linked


def get_document_events(doc_id: int) -> List[Dict]:
    """Get all events for a document."""
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        events = session.query(KbEvent).filter(KbEvent.doc_id == doc_id).order_by(
            KbEvent.event_date.desc().nullslast(), KbEvent.id
        ).all()
        return [_event_to_dict(e, session) for e in events]
    finally:
        session.close()


def get_event_detail(event_id: int) -> Optional[Dict]:
    """Get event detail with linked entities."""
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        event = session.query(KbEvent).filter(KbEvent.id == event_id).first()
        if not event:
            return None
        return _event_to_dict(event, session)
    finally:
        session.close()


def search_events_by_entity(entity_name: str, limit: int = 20) -> List[Dict]:
    """Find events linked to a specific entity."""
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        # Find entity
        entities = session.query(KbEntity).filter(
            KbEntity.name.ilike(f"%{entity_name}%")
        ).limit(5).all()

        if not entities:
            return []

        entity_ids = [e.id for e in entities]
        links = session.query(KbEventEntity).filter(
            KbEventEntity.entity_id.in_(entity_ids)
        ).limit(limit * 2).all()

        event_ids = list(set(l.entity_id for l in links))[:limit]
        events = session.query(KbEvent).filter(KbEvent.id.in_(event_ids)).all()
        return [_event_to_dict(e, session) for e in events]
    finally:
        session.close()


def _event_to_dict(event: KbEvent, session) -> Dict:
    """Convert KbEvent ORM object to dict."""
    # Get linked entity names
    links = session.query(KbEventEntity).filter(
        KbEventEntity.event_id == event.id
    ).all()
    entity_ids = [l.entity_id for l in links]
    entities = []
    if entity_ids:
        kb_entities = session.query(KbEntity).filter(
            KbEntity.id.in_(entity_ids)
        ).all()
        entities = [{"id": e.id, "name": e.name, "type": e.entity_type} for e in kb_entities]

    # Get document title from SQLite
    doc_title = ""
    try:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            doc = db.query(DmsDocument).filter(DmsDocument.id == event.doc_id).first()
            if doc:
                doc_title = doc.title
    except Exception:
        pass

    return {
        "id": event.id,
        "doc_id": event.doc_id,
        "doc_title": doc_title,
        "title": event.title,
        "description": event.description,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "event_type": event.event_type,
        "attributes": event.attributes,
        "entities": entities,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }

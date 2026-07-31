"""
Knowledge Base Relation Ingestion Pipeline.

Extract entity relations from documents → find-or-create entities in
dms_entities → store relations in dms_entity_relations (SQLite, source of
truth) → mirror to KB PostgreSQL via sync_all_to_kb().

Note: dms_entity_relations is the source table; kb_entity_relations is a
read-only mirror. Always write to dms and sync, never write kb directly.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("materialhub.kb_relation_ingest")

# Map extraction entity types to DMS entity types (DMS uses org/person)
_ETYPE_MAP = {"organization": "org", "company": "org", "person": "person"}

# Known name aliases: normalized alias → canonical name (dedup person/org variants)
_ALIASES = {
    "zefengji": "纪泽丰",
    "琪信通达": "琪信通达(北京)科技有限公司",
}


def _norm(s: str) -> str:
    """Normalize an entity name for dedup: full-width→half-width parens, strip spaces, lowercase."""
    return (s or "").replace("（", "(").replace("）", ")").replace(" ", "").strip().lower()


def ingest_relations_for_document(doc_id: int) -> int:
    """Extract relations from a document and store in dms_entity_relations.

    Args:
        doc_id: SQLite dms_documents.id

    Returns:
        Number of relations created (deduplicated against existing).
    """
    try:
        from kb_extraction import extract_relations_from_document
        relations = extract_relations_from_document(doc_id)
    except Exception as e:
        logger.warning("Relation extraction failed for doc %d: %s", doc_id, e)
        return 0

    if not relations:
        logger.info("Document %d: no relations extracted", doc_id)
        return 0

    from dms_models import get_dms_session, EntityRelation

    created = 0
    with get_dms_session() as session:
        for rel in relations:
            try:
                from_entity = _find_or_create_entity(session, rel["from_name"], rel.get("from_type"))
                to_entity = _find_or_create_entity(session, rel["to_name"], rel.get("to_type"))
                if not from_entity or not to_entity:
                    continue

                # Skip self-relations
                if from_entity.id == to_entity.id:
                    continue

                # Dedup against unique constraint uq_entity_rel(from_id, to_id, relation)
                existing = session.query(EntityRelation).filter(
                    EntityRelation.from_id == from_entity.id,
                    EntityRelation.to_id == to_entity.id,
                    EntityRelation.relation == rel["relation"],
                ).first()
                if existing:
                    continue

                attrs = {"source": "auto_extraction", "doc_id": doc_id}
                if rel.get("description"):
                    attrs["description"] = rel["description"]
                if rel.get("confidence") is not None:
                    attrs["confidence"] = rel["confidence"]

                session.add(EntityRelation(
                    from_id=from_entity.id,
                    to_id=to_entity.id,
                    relation=rel["relation"],
                    attributes=json.dumps(attrs, ensure_ascii=False),
                ))
                created += 1
            except Exception as e:
                logger.warning("Failed to store relation %s->%s: %s",
                               rel.get("from_name"), rel.get("to_name"), e)
                continue

    if created:
        # Mirror dms relations (and any new entities) to KB PostgreSQL
        try:
            from kb_entity_sync import sync_all_to_kb
            sync_all_to_kb()
        except Exception as e:
            logger.warning("KB relation sync failed for doc %d (non-fatal): %s", doc_id, e)

    logger.info("Document %d: %d relations stored", doc_id, created)
    return created


def _find_or_create_entity(session, name: str, etype: Optional[str]):
    """Find or create a dms Entity by (entity_type, name).

    Applies alias resolution + normalized substring matching so name variants
    (琪信通达 vs 琪信通达(北京)科技有限公司, Zefeng Ji vs 纪泽丰) map to the
    same entity instead of creating duplicates.
    """
    if not name or len(name.strip()) < 2:
        return None
    from dms_models import Entity

    name = name.strip()
    dms_type = _ETYPE_MAP.get((etype or "").strip().lower(), (etype or "subject").strip().lower())

    # Alias resolution (known variants)
    canonical = _ALIASES.get(_norm(name))
    if canonical:
        name = canonical

    # 1. Exact match
    entity = session.query(Entity).filter(
        Entity.entity_type == dms_type,
        Entity.name == name,
    ).first()
    if entity:
        return entity

    # 2. Normalized substring match for org/person (short name ⊂ full name or vice versa)
    nn = _norm(name)
    if dms_type in ("org", "person"):
        best = None
        for c in session.query(Entity).filter(Entity.entity_type == dms_type).all():
            cn = _norm(c.name)
            if not cn or not nn:
                continue
            shorter, longer = (nn, cn) if len(nn) <= len(cn) else (cn, nn)
            if len(shorter) >= 3 and shorter in longer:
                if best is None or abs(len(cn) - len(nn)) < abs(len(_norm(best.name)) - len(nn)):
                    best = c
        if best:
            return best

    # 3. Create new
    entity = Entity(entity_type=dms_type, name=name)
    session.add(entity)
    session.flush()
    logger.info("Created entity (relation extraction): %s '%s'", dms_type, name)
    return entity

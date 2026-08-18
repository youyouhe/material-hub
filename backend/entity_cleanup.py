"""Orphan entity cleanup after document deletion.

Entities are shared across documents, so deleting a document must not cascade
into them — but an entity left with no document links, no entity relations and
no bid-team membership is dead weight, and historically kept stale (or
mock-generated) profile data alive after its source document was deleted.
"""

import logging

from dms_models import Entity, DocumentEntity, EntityRelation, BidTeamMember

logger = logging.getLogger("materialhub.entity_cleanup")


def cleanup_orphan_entities(session, entity_ids) -> list:
    """Delete entities that lost their last supporting document.

    An entity is kept if anything still references it: other documents,
    entity relations, or a bid-team membership. KB mirror rows are removed
    best-effort. Returns the names of removed entities.
    """
    removed = []
    for eid in set(entity_ids or []):
        entity = session.query(Entity).filter(Entity.id == eid).first()
        if not entity:
            continue
        if session.query(DocumentEntity).filter(DocumentEntity.entity_id == eid).first():
            continue
        has_relation = session.query(EntityRelation).filter(
            (EntityRelation.from_id == eid) | (EntityRelation.to_id == eid)
        ).first()
        if has_relation:
            continue
        if session.query(BidTeamMember).filter(BidTeamMember.entity_id == eid).first():
            continue
        removed.append(entity.name)
        session.delete(entity)
        try:
            from kb_entity_sync import delete_entity_from_kb
            delete_entity_from_kb(eid)
        except Exception as e:
            logger.warning(f"KB entity delete failed for {eid} (non-fatal): {e}")
    if removed:
        logger.info(f"Removed orphan entities after document delete: {removed}")
    return removed

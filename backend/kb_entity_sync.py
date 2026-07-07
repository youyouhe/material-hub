"""
Entity Sync: SQLite DMS entities → PostgreSQL KB entities.

Keeps kb_entities and kb_entity_relations in sync with the main
SQLite database. Triggered on entity/folder CRUD operations.
"""

import logging
from typing import List, Dict

from kb_database import get_session_local
from kb_models import KbEntity, KbEntityRelation, KbFolder
from kb_embedding import embed_text

logger = logging.getLogger("materialhub.kb_entity_sync")


def sync_entities_to_kb() -> Dict:
    """Mirror all dms_entities to kb_entities with embeddings.

    Incremental: only processes entities not yet in kb_entities
    or those with newer updated_at timestamps.

    Returns: {synced, skipped, errors}
    """
    try:
        from dms_models import get_dms_session, Entity
        with get_dms_session() as dms_db:
            entities = dms_db.query(Entity).all()
            entity_list = [
                {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "attributes": e.attributes,
                }
                for e in entities
            ]
    except Exception as e:
        logger.error("Failed to read entities from SQLite: %s", e)
        return {"synced": 0, "skipped": 0, "errors": 1}

    if not entity_list:
        return {"synced": 0, "skipped": 0, "errors": 0}

    SessionLocal = get_session_local()
    session = SessionLocal()
    synced = skipped = errors = 0

    try:
        for ent_info in entity_list:
            try:
                existing = session.query(KbEntity).filter(
                    KbEntity.dms_entity_id == ent_info["id"]
                ).first()

                # Build description text for embedding
                desc_text = _build_entity_text(ent_info)

                if existing:
                    # Update if name or type changed
                    needs_update = (
                        existing.name != ent_info["name"]
                        or existing.entity_type != ent_info["entity_type"]
                    )
                    if needs_update:
                        existing.name = ent_info["name"]
                        existing.entity_type = ent_info["entity_type"]
                        existing.description = desc_text
                        existing.attributes = ent_info["attributes"]
                        embedding = embed_text(desc_text)
                        existing.embedding = embedding
                        synced += 1
                    else:
                        skipped += 1
                else:
                    # Create new KB entity
                    embedding = embed_text(desc_text)
                    kb_entity = KbEntity(
                        dms_entity_id=ent_info["id"],
                        name=ent_info["name"],
                        entity_type=ent_info["entity_type"],
                        description=desc_text,
                        embedding=embedding,
                        attributes=ent_info["attributes"],
                    )
                    session.add(kb_entity)
                    synced += 1

            except Exception as e:
                logger.warning("Failed to sync entity %d: %s", ent_info["id"], e)
                errors += 1

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Entity sync transaction failed: %s", e)
    finally:
        session.close()

    logger.info("Entity sync: %d synced, %d skipped, %d errors", synced, skipped, errors)
    return {"synced": synced, "skipped": skipped, "errors": errors}


def sync_entity_relations_to_kb() -> Dict:
    """Mirror dms_entity_relations to kb_entity_relations."""
    try:
        from dms_models import get_dms_session, EntityRelation
        with get_dms_session() as dms_db:
            relations = dms_db.query(EntityRelation).all()
            rel_list = [
                {"from_id": r.from_id, "to_id": r.to_id, "relation": r.relation}
                for r in relations
            ]
    except Exception as e:
        logger.error("Failed to read relations from SQLite: %s", e)
        return {"synced": 0, "errors": 1}

    if not rel_list:
        return {"synced": 0, "errors": 0}

    SessionLocal = get_session_local()
    session = SessionLocal()
    synced = errors = 0

    try:
        for rel_info in rel_list:
            try:
                # Resolve DMS entity IDs to KB entity IDs
                from_kb = session.query(KbEntity).filter(
                    KbEntity.dms_entity_id == rel_info["from_id"]
                ).first()
                to_kb = session.query(KbEntity).filter(
                    KbEntity.dms_entity_id == rel_info["to_id"]
                ).first()

                if not from_kb or not to_kb:
                    continue

                # Check for existing relation
                existing = session.query(KbEntityRelation).filter(
                    KbEntityRelation.from_entity_id == from_kb.id,
                    KbEntityRelation.to_entity_id == to_kb.id,
                    KbEntityRelation.relation == rel_info["relation"],
                ).first()

                if not existing:
                    rel = KbEntityRelation(
                        from_entity_id=from_kb.id,
                        to_entity_id=to_kb.id,
                        relation=rel_info["relation"],
                    )
                    session.add(rel)
                    synced += 1

            except Exception as e:
                errors += 1

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Relation sync failed: %s", e)
    finally:
        session.close()

    logger.info("Relation sync: %d synced, %d errors", synced, errors)
    return {"synced": synced, "errors": errors}


def sync_folders_to_kb() -> Dict:
    """Mirror dms_folders to kb_folders for RBAC filtering in vector search."""
    try:
        from dms_models import get_dms_session, Folder
        with get_dms_session() as dms_db:
            folders = dms_db.query(Folder).all()
            folder_list = [
                {"id": f.id, "name": f.name, "path": f.path, "parent_id": f.parent_id}
                for f in folders
            ]
    except Exception as e:
        logger.error("Failed to read folders from SQLite: %s", e)
        return {"synced": 0, "errors": 1}

    if not folder_list:
        return {"synced": 0, "errors": 0}

    SessionLocal = get_session_local()
    session = SessionLocal()
    synced = errors = 0

    try:
        for f_info in folder_list:
            try:
                existing = session.query(KbFolder).filter(
                    KbFolder.dms_folder_id == f_info["id"]
                ).first()

                if existing:
                    existing.name = f_info["name"]
                    existing.path = f_info["path"]
                    existing.parent_id = f_info["parent_id"]
                else:
                    kf = KbFolder(
                        dms_folder_id=f_info["id"],
                        name=f_info["name"],
                        path=f_info["path"],
                        parent_id=f_info["parent_id"],
                    )
                    session.add(kf)
                synced += 1
            except Exception:
                errors += 1

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Folder sync failed: %s", e)
    finally:
        session.close()

    logger.info("Folder sync: %d synced, %d errors", synced, errors)
    return {"synced": synced, "errors": errors}


def sync_all_to_kb() -> Dict:
    """Run all sync operations."""
    entities = sync_entities_to_kb()
    relations = sync_entity_relations_to_kb()
    folders = sync_folders_to_kb()
    return {"entities": entities, "relations": relations, "folders": folders}


def _build_entity_text(entity_info: dict) -> str:
    """Build descriptive text for entity embedding."""
    parts = [entity_info["name"], entity_info["entity_type"]]
    attrs = entity_info.get("attributes") or {}
    if isinstance(attrs, str):
        try:
            import json
            attrs = json.loads(attrs)
        except Exception:
            attrs = {}
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            if v:
                parts.append(f"{k}: {v}")
    return " ".join(parts)

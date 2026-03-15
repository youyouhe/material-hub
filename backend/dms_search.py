"""
DMS Full-Text Search using SQLite FTS5.

Provides document indexing and keyword search with BM25 ranking.
Uses the unicode61 tokenizer for Chinese/English mixed text support.
"""

import json
import logging
import os
from typing import Optional

from sqlalchemy import text

from dms_models import get_dms_session, DmsDocument, DocumentEntity, DocumentTag

logger = logging.getLogger("materialhub.dms_search")

FTS_TABLE = "dms_search_index"


def init_fts_table():
    """Create the FTS5 virtual table if it doesn't exist."""
    with get_dms_session() as session:
        session.execute(text(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE}
            USING fts5(
                doc_id UNINDEXED,
                title,
                ocr_text,
                entity_names,
                tags,
                folder_path,
                doc_type_name,
                tokenize='unicode61'
            )
        """))
    logger.info("FTS5 table '%s' initialized", FTS_TABLE)


def _extract_ocr_text(doc: DmsDocument) -> str:
    """Extract searchable OCR text from document meta_json."""
    if not doc.meta_json:
        return ""
    try:
        meta = json.loads(doc.meta_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    parts = []
    # Summary from LLM
    summary = meta.get("summary", "")
    if summary:
        parts.append(summary)

    # Extracted data fields (flatten values)
    extracted = meta.get("extracted_data", {})
    if isinstance(extracted, dict):
        for v in extracted.values():
            if isinstance(v, str) and v:
                parts.append(v)

    return " ".join(parts)


def _get_entity_names(doc: DmsDocument) -> str:
    """Get space-separated entity names linked to document."""
    names = []
    for link in doc.entity_links:
        if link.entity and link.entity.name:
            names.append(link.entity.name)
    return " ".join(names)


def _get_tag_names(doc: DmsDocument) -> str:
    """Get space-separated tag names linked to document."""
    names = []
    for link in doc.tag_links:
        if link.tag and link.tag.name:
            names.append(link.tag.name)
    return " ".join(names)


def index_document(doc_id: int):
    """Index or re-index a single document in the FTS table."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            logger.warning("Cannot index doc %d: not found", doc_id)
            return

        title = doc.title or ""
        ocr_text = _extract_ocr_text(doc)
        entity_names = _get_entity_names(doc)
        tag_names = _get_tag_names(doc)
        folder_path = doc.folder.path if doc.folder else ""
        doc_type_name = doc.doc_type.name if doc.doc_type else ""

        # Remove existing entry
        session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )

        # Insert new entry
        session.execute(
            text(f"""
                INSERT INTO {FTS_TABLE} (doc_id, title, ocr_text, entity_names, tags, folder_path, doc_type_name)
                VALUES (:doc_id, :title, :ocr_text, :entity_names, :tags, :folder_path, :doc_type_name)
            """),
            {
                "doc_id": doc_id,
                "title": title,
                "ocr_text": ocr_text,
                "entity_names": entity_names,
                "tags": tag_names,
                "folder_path": folder_path,
                "doc_type_name": doc_type_name,
            },
        )

    logger.info("Indexed doc %d in FTS", doc_id)


def remove_from_index(doc_id: int):
    """Remove a document from the FTS index."""
    with get_dms_session() as session:
        session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
    logger.info("Removed doc %d from FTS index", doc_id)


def rebuild_index() -> int:
    """Drop and rebuild the entire FTS index. Returns count of indexed documents."""
    with get_dms_session() as session:
        # Clear existing index
        session.execute(text(f"DELETE FROM {FTS_TABLE}"))

        # Get all active and draft documents
        docs = session.query(DmsDocument).filter(
            DmsDocument.status.in_(["active", "draft"])
        ).all()

        count = 0
        for doc in docs:
            title = doc.title or ""
            ocr_text = _extract_ocr_text(doc)
            entity_names = _get_entity_names(doc)
            tag_names = _get_tag_names(doc)
            folder_path = doc.folder.path if doc.folder else ""
            doc_type_name = doc.doc_type.name if doc.doc_type else ""

            session.execute(
                text(f"""
                    INSERT INTO {FTS_TABLE} (doc_id, title, ocr_text, entity_names, tags, folder_path, doc_type_name)
                    VALUES (:doc_id, :title, :ocr_text, :entity_names, :tags, :folder_path, :doc_type_name)
                """),
                {
                    "doc_id": doc.id,
                    "title": title,
                    "ocr_text": ocr_text,
                    "entity_names": entity_names,
                    "tags": tag_names,
                    "folder_path": folder_path,
                    "doc_type_name": doc_type_name,
                },
            )
            count += 1

    logger.info("FTS index rebuilt: %d documents indexed", count)
    return count


def _build_fts_query(raw_query: str) -> str:
    """Build an FTS5 query with prefix matching for partial/fuzzy search.

    Transforms user input into FTS5 syntax:
    - Each token gets a '*' suffix for prefix matching
    - Multiple tokens are combined with implicit AND
    - Special FTS5 characters are escaped
    """
    import re
    # Remove FTS5 special syntax characters to prevent injection
    cleaned = re.sub(r'["\(\)\{\}\[\]:^~]', ' ', raw_query)
    tokens = cleaned.split()
    if not tokens:
        return raw_query

    parts = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # Each token becomes a prefix query
        parts.append(f'"{token}"*')

    return " ".join(parts)


def _like_fallback_search(session, raw_query: str, limit: int) -> list[int]:
    """Fallback LIKE-based substring search when FTS returns insufficient results.

    Searches title, ocr_text, and entity_names columns using SQL LIKE '%query%'.
    """
    pattern = f"%{raw_query}%"
    results = session.execute(
        text(f"""
            SELECT DISTINCT doc_id FROM {FTS_TABLE}
            WHERE title LIKE :pattern
               OR ocr_text LIKE :pattern
               OR entity_names LIKE :pattern
               OR tags LIKE :pattern
               OR folder_path LIKE :pattern
               OR doc_type_name LIKE :pattern
            LIMIT :limit
        """),
        {"pattern": pattern, "limit": limit},
    ).fetchall()
    return [r[0] for r in results]


def search_index(query: str, limit: int = 50, offset: int = 0):
    """
    Search the FTS index with BM25 ranking and partial matching.

    Uses FTS5 prefix queries first, then falls back to LIKE search
    if not enough results are found.

    Returns list of dicts: [{doc_id, rank, snippet}, ...]
    """
    fts_query = _build_fts_query(query)

    with get_dms_session() as session:
        # Phase 1: FTS5 prefix MATCH with BM25 ranking
        fts_doc_ids = []
        details = {}
        try:
            results = session.execute(
                text(f"""
                    SELECT doc_id, rank,
                           snippet({FTS_TABLE}, 1, '<b>', '</b>', '...', 32) as title_snippet,
                           snippet({FTS_TABLE}, 2, '<b>', '</b>', '...', 64) as ocr_snippet
                    FROM {FTS_TABLE}
                    WHERE {FTS_TABLE} MATCH :query
                    ORDER BY rank
                    LIMIT :limit OFFSET :offset
                """),
                {"query": fts_query, "limit": limit, "offset": offset},
            ).fetchall()

            fts_doc_ids = [r[0] for r in results]
            details = {
                r[0]: {
                    "rank": r[1],
                    "snippet": r[3] if r[3] else r[2],
                }
                for r in results
            }
        except Exception as e:
            logger.warning("FTS5 MATCH failed for query '%s': %s", fts_query, e)

        # Phase 2: LIKE fallback if FTS returned too few results
        like_ids = []
        if len(fts_doc_ids) < limit:
            remaining = limit - len(fts_doc_ids)
            like_ids = _like_fallback_search(session, query, remaining + offset)
            # Remove duplicates already found by FTS
            fts_set = set(fts_doc_ids)
            like_ids = [did for did in like_ids if did not in fts_set]
            for did in like_ids:
                details[did] = {"rank": 0, "snippet": None}

        all_ids = fts_doc_ids + like_ids

        # Total count: FTS count + LIKE-only count
        total = 0
        try:
            total_row = session.execute(
                text(f"""
                    SELECT COUNT(*) FROM {FTS_TABLE}
                    WHERE {FTS_TABLE} MATCH :query
                """),
                {"query": fts_query},
            ).fetchone()
            total = total_row[0] if total_row else 0
        except Exception:
            pass

        if like_ids:
            total = max(total, len(all_ids))

        return {
            "doc_ids": all_ids,
            "details": details,
            "total": total,
        }

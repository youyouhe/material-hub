"""
Knowledge Base Search.

Vector search and hybrid search (RRF fusion of vector + FTS5 results).
Ported from SAG's search pipeline, adapted for MaterialHub's dual-DB architecture.
"""

import logging
from typing import List, Dict, Optional

from sqlalchemy import text

from kb_database import get_engine
from kb_embedding import embed_text

logger = logging.getLogger("materialhub.kb_search")

# Reciprocal Rank Fusion constant
RRF_K = 60


def vector_search(
    query: str,
    top_k: int = 20,
    allowed_folder_ids: Optional[List[int]] = None,
    threshold: float = 0.0,
) -> List[Dict]:
    """Pure vector similarity search over KB chunks.

    Uses pgvector cosine similarity (<=> operator).

    Args:
        query: search query text
        top_k: max results to return
        allowed_folder_ids: optional list of folder IDs for RBAC filtering
        threshold: minimum cosine similarity (0-1), lower = more inclusive

    Returns:
        List of result dicts with: doc_id, chunk_id, content, score, heading_path
    """
    query_vector = embed_text(query)
    engine = get_engine()

    # Build RBAC folder filter
    folder_filter = ""
    folder_params: dict = {}

    if allowed_folder_ids is not None:
        if not allowed_folder_ids:
            return []  # No access to any folder
        # Build IN clause with numbered params
        folder_placeholders = []
        for i, fid in enumerate(allowed_folder_ids):
            pname = f"fid_{i}"
            folder_params[pname] = fid
            folder_placeholders.append(f":{pname}")
        folder_filter = f"""
            AND EXISTS (
                SELECT 1 FROM kb_folders kf
                WHERE kf.dms_folder_id IN ({', '.join(folder_placeholders)})
            )
        """

    # pgvector requires vector literals embedded in SQL, not parameterized
    vector_literal = _to_vector_str(query_vector)

    sql = f"""
        SELECT
            kc.doc_id,
            kc.id AS chunk_id,
            kc.content,
            kc.heading_path,
            1.0 - (kc.embedding <=> '{vector_literal}') AS similarity
        FROM kb_chunks kc
        WHERE kc.embedding IS NOT NULL
          AND 1.0 - (kc.embedding <=> '{vector_literal}') >= :threshold
          {folder_filter}
        ORDER BY kc.embedding <=> '{vector_literal}'
        LIMIT :top_k
    """

    params = {"threshold": threshold, "top_k": min(top_k, 50)}
    params.update(folder_params)

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
    except Exception as e:
        logger.error("Vector search failed: %s", e)
        return []

    # Enrich with document metadata from SQLite
    results = []
    for row in rows:
        doc_info = _get_doc_info(row[0])
        results.append({
            "doc_id": row[0],
            "chunk_id": row[1],
            "content": row[2],
            "heading_path": row[3],
            "score": round(float(row[4]), 4),
            "title": doc_info.get("title", ""),
            "doc_type": doc_info.get("doc_type", ""),
            "folder": doc_info.get("folder", ""),
            "entity_names": doc_info.get("entity_names", []),
        })

    # Sort by similarity descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def hybrid_search(
    query: str,
    top_k: int = 20,
    allowed_folder_ids: Optional[List[int]] = None,
) -> List[Dict]:
    """Hybrid search combining vector similarity with FTS5 keyword results.

    Uses Reciprocal Rank Fusion (RRF) to merge ranking signals:
      RRF_score(doc) = Σ 1 / (k + rank_i)
      where k = 60 (standard RRF constant)

    Args:
        query: search query text
        top_k: max results to return
        allowed_folder_ids: optional folder IDs for RBAC

    Returns:
        List of result dicts sorted by RRF score
    """
    # Run both searches in parallel (conceptually — Python GIL means sequential)
    vector_results = vector_search(query, top_k=top_k * 2,
                                   allowed_folder_ids=allowed_folder_ids)

    # Run FTS5 search via the existing search pipeline
    fts_results = _fts_search(query, top_k=top_k * 2,
                              allowed_folder_ids=allowed_folder_ids)

    # RRF fusion: compute scores
    rrf_scores: Dict[int, float] = {}  # doc_id → RRF score
    doc_data: Dict[int, Dict] = {}      # doc_id → enriched metadata

    for rank, r in enumerate(vector_results):
        doc_id = r["doc_id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (RRF_K + rank + 1)
        if doc_id not in doc_data:
            doc_data[doc_id] = r

    for rank, r in enumerate(fts_results):
        doc_id = r.get("id") or r.get("doc_id")
        if not doc_id:
            continue
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (RRF_K + rank + 1)
        if doc_id not in doc_data:
            doc_data[doc_id] = {
                "doc_id": doc_id,
                "title": r.get("title", ""),
                "doc_type": r.get("doc_type", ""),
                "folder": r.get("folder", ""),
                "entity_names": r.get("entity_names", []),
                "snippet": r.get("snippet", ""),
                "score": 0.0,
            }

    # Sort by RRF score
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for doc_id, rrf_score in sorted_docs[:top_k]:
        data = doc_data.get(doc_id, {"doc_id": doc_id})
        data["rrf_score"] = round(rrf_score, 6)
        results.append(data)

    return results


def _fts_search(
    query: str,
    top_k: int = 20,
    allowed_folder_ids: Optional[List[int]] = None,
) -> List[Dict]:
    """Thin wrapper around MaterialHub's existing FTS5 search.

    Returns list of {id, title, doc_type, folder, entity_names, snippet}.
    """
    try:
        from dms_search import search_index
        # FTS5 doc_ids in rank order
        doc_ids, details, _ = search_index(query, limit=top_k)
        if not doc_ids:
            return []

        # Get document metadata from SQLite
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            docs = db.query(DmsDocument).filter(DmsDocument.id.in_(doc_ids)).all()
            doc_map = {d.id: d for d in docs}

        results = []
        for doc_id in doc_ids:
            doc = doc_map.get(doc_id)
            if not doc:
                continue

            # Folder RBAC check
            if allowed_folder_ids is not None and doc.folder_id not in allowed_folder_ids:
                continue

            detail = details.get(doc_id, {})
            results.append({
                "id": doc_id,
                "title": doc.title,
                "doc_type": doc.doc_type.name if doc.doc_type else "",
                "folder": doc.folder.path if doc.folder else "",
                "entity_names": [e.entity_name for e in (doc.entities or [])],
                "snippet": detail.get("snippet", ""),
            })

        return results[:top_k]
    except Exception as e:
        logger.warning("FTS search failed during hybrid merge: %s", e)
        return []


def _get_doc_info(doc_id: int) -> Dict:
    """Get document metadata from SQLite by doc_id."""
    try:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            doc = db.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                return {}
            return {
                "title": doc.title,
                "doc_type": doc.doc_type.name if doc.doc_type else "",
                "folder": doc.folder.path if doc.folder else "",
                "entity_names": [e.entity_name for e in (doc.entities or [])][:5],
                "status": doc.status,
            }
    except Exception:
        return {}


def _to_vector_str(vec: List[float]) -> str:
    """Convert embedding vector to pgvector literal string."""
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

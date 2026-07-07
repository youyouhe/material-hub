"""
Multi-Hop Search Pipeline.

Implements SAG's 8-step search pipeline for entity-aware retrieval.
Ported from SAG's src/services/search-service.ts.

Pipeline:
  Step 1: Query vectorization
  Step 2: Entity recall (vector + exact name match)
  Step 3: Event recall (vector search)
  Step 4: Graph expansion (BFS entity traversal)
  Step 5: Chunk retrieval (vector + event-linked chunks)
  Step 6: Coarse ranking (weighted scoring)
  Step 7: Reranking (cross-encoder)
  Step 8: Result assembly (SQLite metadata enrichment)
"""

import logging
from time import perf_counter
from typing import List, Dict, Optional, Set

from kb_embedding import embed_text
from kb_database import get_session_local
from kb_models import KbEntity, KbEvent, KbEventEntity, KbChunk
from kb_graph import expand_entity_graph
from kb_rerank import rerank
from kb_search import vector_search

logger = logging.getLogger("materialhub.kb_multihop")


def multihop_search(
    query: str,
    top_k: int = 10,
    max_hops: int = 2,
    allowed_folder_ids: Optional[List[int]] = None,
) -> Dict:
    """Full multi-hop search pipeline.

    Args:
        query: natural language question
        top_k: max final results
        max_hops: max entity graph expansion depth (1-3)
        allowed_folder_ids: optional folder RBAC filter

    Returns:
        {
            results: [{doc_id, title, content, score, ...}],
            trace: {steps, entities_found, events_found, timings},
        }
    """
    timings: Dict[str, float] = {}
    trace_steps = []
    t0 = perf_counter()

    # ── Step 1: Query Vectorization ──
    query_vector = embed_text(query)
    timings["step1_query_embedding"] = round((perf_counter() - t0) * 1000)

    # ── Step 2: Entity Recall ──
    t1 = perf_counter()
    recalled_entities = _recall_entities(query, query_vector)
    timings["step2_entity_recall"] = round((perf_counter() - t1) * 1000)
    trace_steps.append({
        "step": 2, "name": "实体召回",
        "detail": f"找到 {len(recalled_entities)} 个相关实体",
        "entities": [{"id": e["id"], "name": e["name"], "type": e["entity_type"]} for e in recalled_entities[:10]],
    })

    # ── Step 3: Event Recall ──
    t2 = perf_counter()
    recalled_events = _recall_events(query, query_vector)
    timings["step3_event_recall"] = round((perf_counter() - t2) * 1000)
    trace_steps.append({
        "step": 3, "name": "事件召回",
        "detail": f"找到 {len(recalled_events)} 个相关事件",
        "events": [{"id": e["id"], "title": e["title"]} for e in recalled_events[:10]],
    })

    # ── Step 4: Graph Expansion ──
    t3 = perf_counter()
    seed_entity_ids = [e["id"] for e in recalled_entities]
    graph = {}
    if seed_entity_ids:
        graph = expand_entity_graph(seed_entity_ids, max_depth=max_hops)

    # Collect all entity IDs from graph
    all_entity_ids = set(seed_entity_ids)
    for ent_id in graph.get("entities", {}):
        all_entity_ids.add(ent_id)

    # Collect all event IDs from graph + recall
    all_event_ids = set(e["id"] for e in recalled_events)
    for evt in graph.get("events", []):
        all_event_ids.add(evt["id"])

    timings["step4_graph_expansion"] = round((perf_counter() - t3) * 1000)
    trace_steps.append({
        "step": 4, "name": "图谱扩展",
        "detail": f"扩展至 {len(all_entity_ids)} 个实体, {len(all_event_ids)} 个事件",
        "entities_discovered": len(all_entity_ids) - len(seed_entity_ids),
        "events_discovered": len(graph.get("events", [])),
    })

    # ── Step 5: Chunk Retrieval ──
    t4 = perf_counter()
    chunks = _retrieve_chunks(query_vector, all_entity_ids, all_event_ids, top_k * 3)
    timings["step5_chunk_retrieval"] = round((perf_counter() - t4) * 1000)
    trace_steps.append({
        "step": 5, "name": "切片检索",
        "detail": f"找到 {len(chunks)} 个相关切片",
    })

    # ── Step 6: Coarse Ranking ──
    t5 = perf_counter()
    for chunk in chunks:
        # Score: vector similarity * 0.5 + graph relevance * 0.3 + content length bonus * 0.2
        vector_score = chunk.get("score", 0)
        graph_score = 0.3 if any(
            chunk.get("doc_id") == evt.get("doc_id")
            for evt in graph.get("events", [])
        ) else 0.0
        length_bonus = min(len(chunk.get("content", "")) / 500, 1.0) * 0.2
        chunk["coarse_score"] = round(vector_score * 0.5 + graph_score + length_bonus, 4)

    chunks.sort(key=lambda x: x.get("coarse_score", 0), reverse=True)
    candidates = chunks[:top_k * 3]
    timings["step6_coarse_rank"] = round((perf_counter() - t5) * 1000)
    trace_steps.append({
        "step": 6, "name": "粗排",
        "detail": f"选出 {len(candidates)} 个候选",
    })

    # ── Step 7: Reranking ──
    t6 = perf_counter()
    reranked = rerank(query, candidates, top_k)
    timings["step7_rerank"] = round((perf_counter() - t6) * 1000)
    trace_steps.append({
        "step": 7, "name": "重排",
        "detail": f"最终选出 {len(reranked)} 个结果",
    })

    # ── Step 8: Result Assembly ──
    t7 = perf_counter()
    results = _enrich_results(reranked, all_entity_ids)
    timings["step8_assembly"] = round((perf_counter() - t7) * 1000)

    total_ms = round((perf_counter() - t0) * 1000)
    return {
        "results": results,
        "total": len(results),
        "trace": {
            "query": query,
            "steps": trace_steps,
            "entities_found": len(all_entity_ids),
            "events_found": len(all_event_ids),
            "timings": timings,
            "total_ms": total_ms,
        },
    }


def _recall_entities(query: str, query_vector: List[float]) -> List[Dict]:
    """Recall entities by vector similarity + exact name match.

    Fast mode: uses entity vector search (no LLM key extraction).
    """
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        entities = []

        # Vector recall
        vec_str = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
        from sqlalchemy import text
        from kb_database import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT id, dms_entity_id, name, entity_type,
                       1.0 - (embedding <=> '{vec_str}') AS similarity
                FROM kb_entities
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> '{vec_str}'
                LIMIT 20
            """)).fetchall()
            entities = [
                {"id": r[0], "dms_entity_id": r[1], "name": r[2],
                 "entity_type": r[3], "score": float(r[4])}
                for r in rows
            ]

        # Exact/fuzzy name match
        query_names = _extract_query_names(query)
        for qname in query_names:
            matches = session.query(KbEntity).filter(
                KbEntity.name.ilike(f"%{qname}%")
            ).limit(5).all()
            for m in matches:
                if m.id not in {e["id"] for e in entities}:
                    entities.append({
                        "id": m.id, "dms_entity_id": m.dms_entity_id,
                        "name": m.name, "entity_type": m.entity_type,
                        "score": 1.0,
                    })

        # Sort by score
        entities.sort(key=lambda x: x.get("score", 0), reverse=True)
        return entities[:20]

    finally:
        session.close()


def _recall_events(query: str, query_vector: List[float]) -> List[Dict]:
    """Recall events by vector similarity."""
    vec_str = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    from sqlalchemy import text
    from kb_database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, doc_id, title, event_type,
                   1.0 - (embedding <=> '{vec_str}') AS similarity
            FROM kb_events
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> '{vec_str}'
            LIMIT 20
        """)).fetchall()
        return [
            {"id": r[0], "doc_id": r[1], "title": r[2],
             "event_type": r[3], "score": float(r[4])}
            for r in rows
        ]


def _retrieve_chunks(
    query_vector: List[float],
    entity_ids: Set[int],
    event_ids: Set[int],
    limit: int,
) -> List[Dict]:
    """Retrieve chunks: vector search + event-linked + entity-linked."""
    all_chunks: List[Dict] = []
    seen_docs: Set[int] = set()

    # 1. Vector search chunks
    vec_str = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    from sqlalchemy import text
    from kb_database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, doc_id, content, heading_path,
                   1.0 - (embedding <=> '{vec_str}') AS similarity
            FROM kb_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> '{vec_str}'
            LIMIT {limit}
        """)).fetchall()

    for r in rows:
        chunk = {"id": r[0], "doc_id": r[1], "content": r[2], "heading_path": r[3], "score": float(r[4])}
        if chunk["doc_id"] not in seen_docs:
            all_chunks.append(chunk)
            seen_docs.add(chunk["doc_id"])

    # 2. Event-linked chunks
    if event_ids:
        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            events = session.query(KbEvent).filter(
                KbEvent.id.in_(list(event_ids)[:50])
            ).all()
            event_doc_ids = set(e.doc_id for e in events)
            for doc_id in event_doc_ids:
                if doc_id not in seen_docs:
                    chunk = session.query(KbChunk).filter(
                        KbChunk.doc_id == doc_id
                    ).order_by(KbChunk.chunk_index).first()
                    if chunk:
                        all_chunks.append({
                            "id": chunk.id, "doc_id": chunk.doc_id,
                            "content": chunk.content,
                            "heading_path": chunk.heading_path,
                            "score": 0.5,  # Default graph relevance
                        })
                        seen_docs.add(doc_id)
        finally:
            session.close()

    return all_chunks


def _extract_query_names(query: str) -> List[str]:
    """Extract potential entity names from query text."""
    import re
    names = []
    # Chinese company names
    names.extend(re.findall(r'[一-鿿]{2,}(?:公司|集团|机构|部门|中心|事务所)', query))
    # Quoted names (match content inside Chinese or English quotes)
    names.extend(re.findall(r'[“”「」]([^“”「」]{2,30})[“”「」]', query))
    # Person names (2-3 Chinese chars followed by titles)
    names.extend(re.findall(r'([一-鿿]{2,3})(?:先生|女士|经理|主任|总监|工程师|律师|会计师)', query))
    return list(set(names))


def _enrich_results(chunks: List[Dict], entity_ids: Set[int]) -> List[Dict]:
    """Enrich chunk results with document metadata from SQLite."""
    if not chunks:
        return []

    doc_ids = list(set(c["doc_id"] for c in chunks if c.get("doc_id")))

    # Get doc info from SQLite
    doc_info = {}
    try:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            docs = db.query(DmsDocument).filter(DmsDocument.id.in_(doc_ids)).all()
            for d in docs:
                doc_info[d.id] = {
                    "title": d.title,
                    "status": d.status,
                    "doc_type": d.doc_type.name if d.doc_type else "",
                    "folder": d.folder.path if d.folder else "",
                    "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None,
                    "entity_names": [l.entity.name for l in (d.entity_links or []) if l.entity],
                }
    except Exception:
        pass

    results = []
    for c in chunks:
        info = doc_info.get(c["doc_id"], {})
        results.append({
            "doc_id": c["doc_id"],
            "chunk_id": c.get("id"),
            "title": info.get("title", ""),
            "content": c.get("content", ""),
            "heading_path": c.get("heading_path"),
            "score": c.get("rerank_score") or c.get("coarse_score") or c.get("score", 0),
            "doc_type": info.get("doc_type", ""),
            "folder": info.get("folder", ""),
            "entity_names": info.get("entity_names", []),
            "expiry_date": info.get("expiry_date"),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

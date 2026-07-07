"""
Rerank Service for Multi-Hop Search.

Cross-encoder scoring of candidate documents against a query.
- Remote: qwen3-rerank via /v1/reranks
- Local fallback: lexical overlap scoring

Ported from SAG's rerank-client.ts.
"""

import os
import logging
import time
from typing import List, Dict

import requests

from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.kb_rerank")

RERANK_MODEL = os.getenv("RERANK_MODEL", "qwen3-rerank")
RERANK_TIMEOUT = 30


def rerank(
    query: str,
    candidates: List[Dict],
    top_k: int = 10,
) -> List[Dict]:
    """Rerank candidate documents by relevance to query.

    Tries remote rerank API first, falls back to local lexical scoring.

    Args:
        query: search query
        candidates: list of {id, title, content, score, ...}
        top_k: max results to return

    Returns:
        candidates re-sorted with updated scores, length ≤ top_k
    """
    if not candidates:
        return []

    if top_k >= len(candidates):
        # No point calling reranker if we're keeping everything
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        return candidates

    try:
        return _remote_rerank(query, candidates, top_k)
    except Exception as e:
        logger.warning("Remote rerank unavailable, using local fallback: %s", e)
        return _local_rerank(query, candidates, top_k)


def _remote_rerank(query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
    """Call qwen3-rerank via /v1/reranks endpoint."""
    provider = get_llm_provider()
    base_url = getattr(provider, "base_url", os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))

    # Build rerank URL
    url = _build_rerank_url(base_url)

    # Format documents
    documents = []
    for c in candidates:
        text = f"标题：{c.get('title', '')}\n摘要：{c.get('content', '')[:300]}"
        documents.append(text)

    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": min(top_k, len(documents)),
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=RERANK_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            # Parse results (handle multiple response formats)
            results = data.get("results") or data.get("data") or []
            if isinstance(results, dict):
                results = results.get("results", results.get("documents", []))

            if not results:
                return _local_rerank(query, candidates, top_k)

            # Build reranked output
            reranked = []
            seen = set()
            for r in results:
                if isinstance(r, dict):
                    idx = r.get("index", r.get("document_index", 0))
                    relevance = r.get("relevance_score", r.get("relevanceScore", r.get("score", 0.5)))
                    if idx < len(candidates):
                        c = candidates[idx].copy()
                        c["rerank_score"] = round(float(relevance), 4)
                        key = c.get("doc_id") or c.get("id")
                        if key not in seen:
                            reranked.append(c)
                            seen.add(key)

            if reranked:
                return reranked[:top_k]
            return _local_rerank(query, candidates, top_k)

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            raise
        except Exception:
            raise


def _local_rerank(query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
    """Local lexical overlap reranking fallback.

    Same approach as SAG's localScoreRerank: scores each candidate
    by keyword overlap with the query.
    """
    # Tokenize query
    query_tokens = set()
    for word in query.replace("，", " ").replace(",", " ").split():
        word = word.strip().lower()
        if len(word) >= 2:
            query_tokens.add(word)
    # Also add single Chinese chars
    for ch in query:
        if '一' <= ch <= '鿿':
            query_tokens.add(ch)

    for c in candidates:
        text = (c.get("title", "") + " " + c.get("content", "")).lower()
        # Count matching tokens
        overlap = sum(1 for t in query_tokens if t in text)
        # Add length bonus for exact phrase match
        phrase_bonus = 1.0 if query.lower() in text else 0.0
        c["rerank_score"] = round(overlap / max(len(query_tokens), 1) * 0.5 + phrase_bonus, 4)

    candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return candidates[:top_k]


def _build_rerank_url(base_url: str) -> str:
    """Build rerank endpoint URL from LLM base URL."""
    base = base_url.rstrip("/")
    # Handle common patterns
    if base.endswith("/v1"):
        return f"{base}/reranks"
    elif "/v1" in base:
        return f"{base}/reranks"
    else:
        return f"{base}/v1/reranks"

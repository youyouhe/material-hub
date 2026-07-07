"""
Knowledge Base Embedding Service.

Batch embedding with local deterministic fallback.
Ports SAG's embedding-client.ts pattern to Python.

Uses the existing llm_provider.py embed() method, which:
  - Tries the remote embedding API (OpenAI-compatible /v1/embeddings)
  - Falls back to deterministic hash-based embeddings on failure
"""

import os
import logging
from typing import List

from llm_provider import get_embedding_provider, _deterministic_embedding

EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

logger = logging.getLogger("materialhub.kb_embedding")

# Maximum batch size for embedding API calls
MAX_BATCH_SIZE = 100


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts.

    Uses the configured LLM provider's embedding endpoint.
    Falls back to deterministic local embeddings if the API is unavailable.

    Args:
        texts: list of text strings to embed

    Returns:
        List of embedding vectors (each 1024-dimensional, L2-normalized)
    """
    if not texts:
        return []

    all_embeddings = []

    # Process in batches
    for batch_start in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[batch_start:batch_start + MAX_BATCH_SIZE]
        batch_embeddings = _embed_batch(batch)
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


def _embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a single batch of texts (max MAX_BATCH_SIZE)."""
    try:
        provider = get_embedding_provider()
        embeddings = provider.embed(texts)
        if embeddings and len(embeddings) == len(texts):
            return embeddings
        logger.warning(
            "Embedding API returned %d vectors for %d texts, using fallback",
            len(embeddings) if embeddings else 0, len(texts)
        )
    except Exception as e:
        logger.warning("Embedding API unavailable, using local fallback: %s", e)

    # Local deterministic fallback
    return [_deterministic_embedding(t, EMBEDDING_DIMS) for t in texts]


def embed_text(text: str) -> List[float]:
    """Generate embedding for a single text string."""
    results = embed_texts([text])
    return results[0] if results else _deterministic_embedding(text)

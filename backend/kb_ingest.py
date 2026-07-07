"""
Knowledge Base Ingestion Pipeline.

Handles: document text → chunk → embed → store in PostgreSQL.
Triggered from dms_processor.py after document finalization.
"""

import json
import logging
from typing import List, Dict, Optional

from kb_database import get_session_local
from kb_models import KbChunk
from kb_chunking import chunk_text, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from kb_embedding import embed_texts

logger = logging.getLogger("materialhub.kb_ingest")


def _parse_meta(meta_json) -> dict:
    """Safely parse meta_json which may be stored as a JSON string in SQLite."""
    if meta_json is None:
        return {}
    if isinstance(meta_json, dict):
        return meta_json
    if isinstance(meta_json, str):
        try:
            return json.loads(meta_json)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _get_document_text(doc_id: int) -> Optional[str]:
    """Extract combined text from a DMS document for chunking.

    Priority: meta_json._analysis.combined_text > ocr_text > summary
    """
    try:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            doc = db.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                logger.warning("Document %d not found in SQLite", doc_id)
                return None

            meta = _parse_meta(doc.meta_json)

            # Try combined text from analysis phase
            analysis = meta.get("_analysis", {}) or {}
            if isinstance(analysis, str):
                analysis = _parse_meta(analysis)
            combined = analysis.get("combined_text", "")
            if combined and len(combined) > 50:
                return combined

            # Try OCR text
            ocr_text = meta.get("ocr_text", "")
            if ocr_text and len(ocr_text) > 50:
                return ocr_text

            # Fallback: summary + extracted data as text
            summary = meta.get("summary", "")
            extracted = meta.get("extracted_data", {}) or {}
            if isinstance(extracted, str):
                extracted = _parse_meta(extracted)

            extracted_text = " ".join(
                f"{k}: {v}" for k, v in extracted.items() if v
            )

            combined = f"{summary}\n\n{extracted_text}".strip()
            if combined and len(combined) > 20:
                return combined

            # Last resort: document description
            if doc.description:
                return doc.description

            logger.warning("Document %d has no extractable text for KB indexing", doc_id)
            return None
    except Exception as e:
        logger.error("Failed to get text for document %d: %s", doc_id, e)
        return None


def _set_kb_status(doc_id: int, status: str, error: str = None):
    """Update document's KB indexing status in meta_json."""
    try:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            doc = db.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if doc:
                meta = _parse_meta(doc.meta_json)
                meta["_kb_status"] = status
                if error:
                    meta["_kb_error"] = error
                doc.meta_json = json.dumps(meta) if isinstance(doc.meta_json, str) else meta
                db.commit()
    except Exception as e:
        logger.warning("Failed to update KB status for doc %d: %s", doc_id, e)


def ingest_document_chunks(doc_id: int) -> bool:
    """Chunk a document and store embeddings in PostgreSQL.

    Called after document finalization (FTS indexing complete).
    Non-blocking: failure does not affect document upload.

    Args:
        doc_id: SQLite dms_documents.id

    Returns:
        True if KB indexing succeeded, False otherwise
    """
    try:
        text = _get_document_text(doc_id)
        if not text:
            _set_kb_status(doc_id, "skipped", "No extractable text")
            return False

        # 1. Chunk the text
        chunks = chunk_text(text)
        if not chunks:
            _set_kb_status(doc_id, "skipped", "Chunking produced no chunks")
            return False

        logger.info("Document %d: chunked into %d pieces", doc_id, len(chunks))

        # 2. Batch embed all chunks
        contents = [c["content"] for c in chunks]
        embeddings = embed_texts(contents)

        # 3. Store in PostgreSQL
        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            # Remove existing chunks for this doc (re-indexing)
            session.query(KbChunk).filter(KbChunk.doc_id == doc_id).delete()

            for i, chunk_info in enumerate(chunks):
                kb_chunk = KbChunk(
                    doc_id=doc_id,
                    chunk_index=chunk_info["chunk_index"],
                    content=chunk_info["content"],
                    heading_path=chunk_info.get("heading_path"),
                    token_count=chunk_info["token_count"],
                    embedding=embeddings[i] if i < len(embeddings) else None,
                )
                session.add(kb_chunk)

            session.commit()
            logger.info(
                "Document %d: KB indexed %d chunks successfully", doc_id, len(chunks)
            )
            _set_kb_status(doc_id, "indexed")
            return True

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    except Exception as e:
        logger.warning("KB indexing failed for document %d: %s", doc_id, e)
        _set_kb_status(doc_id, "error", str(e)[:500])
        return False


def delete_document_chunks(doc_id: int):
    """Remove all KB chunks for a document (on delete/archive)."""
    try:
        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            deleted = session.query(KbChunk).filter(KbChunk.doc_id == doc_id).delete()
            session.commit()
            if deleted:
                logger.info("Document %d: removed %d KB chunks", doc_id, deleted)
        finally:
            session.close()
    except Exception as e:
        logger.warning("Failed to delete KB chunks for doc %d: %s", doc_id, e)


def reingest_all_documents() -> Dict:
    """Re-index all active documents through the KB pipeline.

    Returns: {total, indexed, skipped, failed}
    """
    try:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            docs = db.query(DmsDocument).filter(
                DmsDocument.status.in_(["active", "draft"])
            ).all()
            doc_ids = [d.id for d in docs]
    except Exception as e:
        return {"total": 0, "indexed": 0, "skipped": 0, "failed": 0, "error": str(e)}

    result = {"total": len(doc_ids), "indexed": 0, "skipped": 0, "failed": 0}
    for doc_id in doc_ids:
        try:
            if ingest_document_chunks(doc_id):
                result["indexed"] += 1
            else:
                result["skipped"] += 1
        except Exception:
            result["failed"] += 1

    return result


def get_kb_status() -> Dict:
    """Get KB index statistics."""
    try:
        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            chunk_count = session.query(KbChunk).count()
            from sqlalchemy import func
            doc_count = session.query(func.count(func.distinct(KbChunk.doc_id))).scalar()
            return {
                "indexed_documents": doc_count or 0,
                "total_chunks": chunk_count,
                "ok": True,
            }
        finally:
            session.close()
    except Exception as e:
        return {"indexed_documents": 0, "total_chunks": 0, "ok": False, "error": str(e)}

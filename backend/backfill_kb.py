"""
Backfill KB for existing documents: chunk vectorization + event extraction
+ relation extraction.

Activates knowledge for documents uploaded before PostgreSQL was configured
(kb_chunks / kb_events were empty because the pipeline failed then).

Usage:
  cd backend
  DB_PATH=data/materials.db python backfill_kb.py                  # all active/draft docs
  DB_PATH=data/materials.db python backfill_kb.py --doc-ids 1,2,3  # specific docs
"""
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_kb")


def process_doc(doc_id: int) -> dict:
    from kb_entity_sync import sync_entities_to_kb, sync_folders_to_kb
    from kb_ingest import ingest_document_chunks
    from kb_event_ingest import ingest_events_for_document
    from kb_relation_ingest import ingest_relations_for_document

    # Ensure entities/folders are mirrored first so events/relations can link
    sync_entities_to_kb()
    sync_folders_to_kb()
    chunk_ok = ingest_document_chunks(doc_id)
    events = ingest_events_for_document(doc_id) if chunk_ok else 0
    relations = ingest_relations_for_document(doc_id) if chunk_ok else 0
    return {"doc_id": doc_id, "chunk": bool(chunk_ok), "events": events, "relations": relations}


def main():
    ap = argparse.ArgumentParser(description="Backfill KB chunk/event/relation for documents")
    ap.add_argument("--doc-ids", default="", help="comma-separated doc ids; default = all active/draft")
    args = ap.parse_args()

    if args.doc_ids:
        doc_ids = [int(x) for x in args.doc_ids.split(",") if x.strip()]
    else:
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as db:
            doc_ids = [d.id for d in db.query(DmsDocument)
                       .filter(DmsDocument.status.in_(["active", "draft"]))
                       .order_by(DmsDocument.id).all()]

    if not doc_ids:
        logger.info("No documents to backfill.")
        return

    logger.info("Backfilling %d documents...", len(doc_ids))
    from kb_entity_sync import sync_all_to_kb

    results = []
    for i, doc_id in enumerate(doc_ids, 1):
        try:
            r = process_doc(doc_id)
            results.append(r)
            logger.info("[%d/%d] doc %d: chunk=%s events=%d relations=%d",
                        i, len(doc_ids), doc_id, r["chunk"], r["events"], r["relations"])
        except Exception as e:
            logger.warning("[%d/%d] doc %d FAILED: %s", i, len(doc_ids), doc_id, e)

    try:
        sync_all_to_kb()
    except Exception as e:
        logger.warning("Final sync_all_to_kb failed: %s", e)

    chunks_ok = sum(1 for r in results if r["chunk"])
    total_events = sum(r["events"] for r in results)
    total_relations = sum(r["relations"] for r in results)
    logger.info("DONE: %d/%d chunked, %d events, %d relations",
                chunks_ok, len(doc_ids), total_events, total_relations)


if __name__ == "__main__":
    main()

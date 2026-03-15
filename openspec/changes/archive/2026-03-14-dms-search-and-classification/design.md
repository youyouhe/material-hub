## Context

MaterialHub's DMS has documents with OCR-extracted text stored in `meta_json`, entities linked via `DocumentEntity`, and tags via `DocumentTag`. The current search is a simple `title ILIKE` query. Phase 3 adds full-text search across document content, a unified search API with faceted filtering, expiry monitoring, and certificate version matching adapted from the legacy `certificate_matcher.py`.

Key existing modules (read-only, no modifications):
- `certificate_matcher.py` — Legacy certificate matching against Material table (reference for logic, not imported directly)
- `ocr_agent.py` — LLM extraction results stored in `meta_json.extracted_data`
- `dms_processor.py` — Background processing pipeline (will be extended to add indexing + version matching steps)

## Goals / Non-Goals

**Goals:**
- Full-text search using SQLite FTS5 with Chinese text support
- Unified search endpoint with multi-faceted filtering
- Expiry monitoring with alerts and dashboard data
- Certificate version matching adapted to DMS models

**Non-Goals:**
- External search engines (Elasticsearch, Meilisearch) — overkill for current scale
- Real-time search index updates via triggers — batch indexing is sufficient
- UI for search (Phase 6)
- Cross-document deduplication beyond version matching

## Decisions

### 1. SQLite FTS5 for full-text search

**Decision**: Use SQLite FTS5 virtual table with the `unicode61` tokenizer (handles Chinese text via Unicode word-break rules). The FTS table stores document_id, title, ocr_text (combined from meta_json), entity_names, and tags.

**Rationale**: FTS5 is built into SQLite, requires no external dependencies, and provides fast full-text search with ranking (BM25). The `unicode61` tokenizer handles CJK characters well enough for our use case (splits on Unicode boundaries). No need for ICU or Jieba — the documents contain mixed Chinese/English and the tokenizer handles both.

**Alternative considered**: SQLite FTS5 with `trigram` tokenizer for substring matching. Not needed — keyword search is sufficient for bid material lookup.

### 2. Search index as a separate FTS5 virtual table

**Decision**: Create `dms_search_index` as an FTS5 external content table pointing to `dms_documents`. Columns: `title`, `ocr_text`, `entity_names`, `tags`. The index is populated/updated after document processing completes and on manual rebuild.

**Rationale**: External content table avoids data duplication — the FTS index references data from the main tables. Rebuild is a single `INSERT INTO ... SELECT` query. Index updates happen at the end of the processing pipeline (after OCR/LLM) and when documents are approved/edited.

### 3. Unified search endpoint with ranked results

**Decision**: `GET /api/v2/search` accepts `q` (keyword), `folder_id`, `doc_type_id`, `entity_id`, `tag_id`, `status`, `expiry_before`, `expiry_after`, `sort` (relevance/date/title), `limit`, `offset`. When `q` is provided, FTS5 is used with BM25 ranking. When `q` is empty, it falls back to standard SQL filtering.

**Rationale**: One endpoint for all search needs. The existing `GET /api/v2/documents/` continues to work for simple listing. The new search endpoint adds FTS, relevance ranking, and combined filters.

### 4. Expiry monitoring as dedicated endpoints

**Decision**: Three endpoints under `/api/v2/expiry/`:
- `GET /summary` — counts by category (expiring within 30/60/90 days, already expired, by DocType)
- `GET /expiring` — documents expiring within N days (default 30)
- `GET /expired` — already-expired documents still in active status

**Rationale**: Expiry monitoring is a distinct concern from search. Dedicated endpoints are simpler to consume for dashboard widgets. The summary endpoint provides aggregated data without returning full document lists.

### 5. Version matching in the upload pipeline

**Decision**: After entity linking in `dms_processor.py`, add a version matching step. For document types that support versioning (business-license, iso-cert, qualification-cert, professional-cert), look for an existing DmsDocument with the same entity + DocType. If found, compare expiry/issue dates. If the new document is newer, create it as a new Revision on the existing Document instead of a standalone document.

**Rationale**: This reuses the proven logic from `certificate_matcher.py` but targets DMS models. Creating a new Revision (instead of a new Document) keeps the document history unified and avoids duplicates. The matching uses entity name + DocType code as the primary key, with date comparison for version ordering.

**Key difference from legacy**: The legacy matcher created a `MaterialVersion` record. The DMS approach creates a proper `Revision` on the same `Document`, moves the files to the new revision, and the old revision remains as history.

### 6. Index rebuild strategy

**Decision**: Provide `POST /api/v2/search/rebuild-index` (admin-only) to rebuild the entire FTS index. Index updates happen incrementally: after processing pipeline completes, after document approve/edit, and after document delete.

**Rationale**: Full rebuild is needed for initial setup and recovery. Incremental updates keep the index fresh during normal operations. The rebuild is fast for our scale (< 10,000 documents).

## Risks / Trade-offs

**[FTS5 unicode61 tokenizer for Chinese]** → May not be as accurate as a dedicated Chinese tokenizer (like Jieba). Mitigation: For our use case (searching company names, certificate types, numbers), word-boundary tokenization is sufficient. If needed, can switch to ICU tokenizer later.

**[Version matching false positives]** → Auto-matching could incorrectly link unrelated documents. Mitigation: Only applies to specific DocTypes (certificates, licenses). Matching requires exact entity match AND DocType match. The document stays in "draft" status so users can review before approving.

**[FTS index staleness]** → If the processing pipeline fails after OCR but before indexing, the document won't appear in search. Mitigation: The index rebuild endpoint can fix this. Also, the document is still findable via direct listing endpoints.

## 1. Full-Text Search Index

- [x] 1.1 Create `dms_search.py` module with FTS5 table creation (`dms_search_index` with columns: doc_id, title, ocr_text, entity_names, tags) using `unicode61` tokenizer
- [x] 1.2 Implement `index_document(doc_id)` function that extracts title, OCR text from meta_json, entity names, and tag names and inserts/updates the FTS row
- [x] 1.3 Implement `remove_from_index(doc_id)` function that deletes the FTS row
- [x] 1.4 Implement `rebuild_index()` function that drops and recreates the entire FTS index from all active/draft documents
- [x] 1.5 Implement `search_index(query, limit, offset)` function that runs FTS5 MATCH with BM25 ranking, returns doc_ids with scores and snippets
- [x] 1.6 Call `init_fts_table()` from `init_dms_db()` in `dms_models.py` to ensure FTS table exists on startup
- [x] 1.7 Add `index_document()` call at the end of `dms_processor.py` processing pipeline (after "completed" status)

## 2. Unified Search API

- [x] 2.1 Create `routers/v2_search.py` with `GET /api/v2/search` endpoint accepting: q, folder_id, doc_type_id, entity_id, tag_id, status, expiry_before, expiry_after, sort, limit, offset
- [x] 2.2 Implement keyword search path: when `q` is provided, query FTS5 for matching doc_ids with BM25 ranking, then apply SQL facet filters on the result set
- [x] 2.3 Implement facet-only search path: when `q` is empty, use standard SQL filters on DmsDocument with ORDER BY updated_at desc
- [x] 2.4 Implement search result formatting: include doc ID, title, status, DocType, folder, entity names, expiry_date, thumbnail URL, snippet (from FTS highlight)
- [x] 2.5 Add `POST /api/v2/search/rebuild-index` endpoint that calls `rebuild_index()` and returns indexed count
- [x] 2.6 Register search router in `main.py`

## 3. Expiry Monitoring

- [x] 3.1 Create `routers/v2_expiry.py` with `GET /api/v2/expiry/summary` — return counts: expiring_30d, expiring_60d, expiring_90d, expired, and by_doc_type breakdown
- [x] 3.2 Add `GET /api/v2/expiry/expiring` — list documents expiring within N days (param `days`, default 30), ordered by soonest first, with pagination
- [x] 3.3 Add `GET /api/v2/expiry/expired` — list active documents with past expiry_date, ordered by oldest first, with pagination
- [x] 3.4 Add `POST /api/v2/expiry/update-status` — batch transition active documents with past expiry_date to "expired" status, return updated count
- [x] 3.5 Register expiry router in `main.py`

## 4. Certificate Version Matching

- [x] 4.1 Create `dms_version_matcher.py` with `find_matching_document(entity_id, doc_type_code, extracted_data, session)` — find existing DmsDocument with same entity + DocType for versionable types
- [x] 4.2 Implement `is_newer_version(new_extracted_data, existing_doc)` — compare expiry/issue dates to determine if new upload is a newer version
- [x] 4.3 Implement `merge_as_revision(existing_doc_id, new_doc_id, session)` — move files from new document's revision to a new revision on the existing document, then delete the standalone new document
- [x] 4.4 Integrate version matching into `dms_processor.py` — after entity linking step, call version matcher for applicable DocTypes; if match found, merge instead of leaving as standalone

## 5. Integration and Testing

- [x] 5.1 End-to-end test: rebuild index, upload a document, verify it appears in FTS search results after processing
- [x] 5.2 End-to-end test: search with combined keyword + facet filters, verify correct filtering and pagination
- [x] 5.3 End-to-end test: expiry monitoring — create documents with various expiry dates, verify summary counts and expiring/expired lists
- [x] 5.4 End-to-end test: version matching — upload two certificates for same entity, verify second becomes a revision of the first
- [x] 5.5 Verify existing v2 endpoints still work (no regressions)

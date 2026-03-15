## ADDED Requirements

### Requirement: FTS5 virtual table for document search index
The system SHALL create an SQLite FTS5 virtual table `dms_search_index` with columns: `doc_id`, `title`, `ocr_text`, `entity_names`, `tags`. The table SHALL use the `unicode61` tokenizer for Chinese/English mixed text support.

#### Scenario: FTS table created on startup
- **WHEN** the application starts and `init_dms_db()` runs
- **THEN** the `dms_search_index` FTS5 virtual table exists in the database

### Requirement: Index documents after processing pipeline completes
The system SHALL index a document into `dms_search_index` when its processing pipeline completes successfully (status = "completed"). The indexed text SHALL include: document title, combined OCR text from `meta_json.extracted_data` and `meta_json.summary`, names of all linked entities, and names of all linked tags.

#### Scenario: Document indexed after OCR processing
- **WHEN** the processing pipeline for document ID=5 completes with OCR text "XX建设有限公司营业执照"
- **THEN** the FTS index contains a row for doc_id=5 with the OCR text searchable

#### Scenario: Document with entities indexed
- **WHEN** document ID=5 has entity "XX建设有限公司" linked
- **THEN** searching for "XX建设" returns document ID=5

### Requirement: Incremental index updates on document changes
The system SHALL update the FTS index when a document is approved (draft→active), when document metadata is edited, or when entity/tag links change. The system SHALL remove a document from the index when it is deleted.

#### Scenario: Index updated on document edit
- **WHEN** document ID=5 title is changed from "营业执照" to "营业执照-2024版"
- **THEN** searching for "2024版" returns document ID=5

#### Scenario: Index entry removed on document delete
- **WHEN** document ID=5 is deleted
- **THEN** searching for content from document ID=5 returns no results

### Requirement: Full index rebuild endpoint
The system SHALL provide `POST /api/v2/search/rebuild-index` that drops and recreates the entire FTS index from all active and draft documents. The endpoint SHALL return the number of documents indexed.

#### Scenario: Rebuild index
- **WHEN** `POST /api/v2/search/rebuild-index` is called
- **THEN** the FTS index is rebuilt from scratch
- **AND** the response includes `{"indexed_count": N}`

### Requirement: FTS search with BM25 ranking
The system SHALL support querying the FTS index using the MATCH operator with BM25 ranking. Search results SHALL be ordered by relevance score (highest first). The system SHALL support searching across all indexed columns or specific columns.

#### Scenario: Search by keyword returns ranked results
- **WHEN** searching for "营业执照" with 3 matching documents
- **THEN** results are returned ordered by BM25 relevance score (most relevant first)

#### Scenario: No results for unmatched keyword
- **WHEN** searching for "不存在的关键词XYZ"
- **THEN** an empty result set is returned

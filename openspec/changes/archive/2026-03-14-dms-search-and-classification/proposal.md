## Why

Phase 2 added document upload and OCR/LLM processing, but search is limited to a simple `title LIKE` query on `GET /api/v2/documents/`. Users need to find documents by OCR-extracted text content, by entity, by expiry status, and by multiple facets simultaneously. Additionally, the existing `certificate_matcher.py` still targets legacy Material tables and needs to be adapted to the DMS model so that uploading a renewed certificate automatically links it to its predecessor as a new Revision.

## What Changes

- Add a **full-text search** capability using SQLite FTS5, indexing document titles, OCR text from meta_json, and entity names — enabling Chinese keyword search across all document content
- Build a **unified search API** (`GET /api/v2/search`) with faceted filtering: keyword, folder, DocType, entity, tag, status, expiry date range, and combined queries
- Add an **expiry monitoring** endpoint that returns documents expiring within N days, already expired, and summary counts per DocType — replacing ad-hoc queries
- Adapt the existing `certificate_matcher.py` to DMS models: when a new document is uploaded with a matching entity + DocType, automatically detect it as a newer version and create a new Revision on the existing Document instead of a duplicate

## Capabilities

### New Capabilities
- `fulltext-search`: SQLite FTS5 index for document content, OCR text, and entity names; index management (build/rebuild); search with Chinese tokenization
- `unified-search-api`: Single search endpoint with faceted filtering, result ranking, highlighting, pagination; replaces the basic `q` parameter on list_documents
- `expiry-monitor`: Endpoints for expiry alerts (expiring-soon, already-expired, summary dashboard data); scheduled expiry status updates

### Modified Capabilities

(none)

## Impact

- **Database**: New FTS5 virtual table `dms_search_index`. No changes to existing DMS tables.
- **Backend**: New file `dms_search.py` (FTS index management), new router `routers/v2_search.py`. Modifications to `dms_processor.py` (index documents after processing). Adaptation of `certificate_matcher.py` logic into a new `dms_version_matcher.py`.
- **Existing APIs**: `GET /api/v2/documents/` keeps working as-is. New `GET /api/v2/search` provides the advanced search. `GET /api/v2/upload/` pipeline gains version matching step.
- **External services**: No new external dependencies. FTS5 is built into SQLite.

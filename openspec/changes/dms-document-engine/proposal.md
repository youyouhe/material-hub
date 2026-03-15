## Why

Phase 1 established the DMS data model (Folder, Document, DocType, Revision, File, Entity, Tag) but there is no way to get documents into the system beyond manual API calls. The existing Smart Import pipeline (`smart_import.py`, `ocr_agent.py`, `auto_processor.py`) still targets the legacy Material/PendingReview tables. Users need a working upload flow that creates proper DMS records, runs OCR/LLM analysis, auto-classifies documents into the right DocType and Folder, and links them to Entities — all through the new v2 API.

## What Changes

- Create a unified DMS upload endpoint (`POST /api/v2/upload/`) that accepts PDF, image, and Word files, creates Document + Revision + File records in one step
- Build a DMS-native processing pipeline (`dms_processor.py`) that replaces the legacy `smart_import.py` flow:
  - PDF: extract selected or all pages as File(type=extracted_page), generate thumbnails
  - Image: store as original, generate thumbnail
  - OCR + LLM: analyze file content, auto-populate Document.meta_json and match DocType
  - Auto-classify: assign Document to the correct Folder based on recognized DocType
  - Entity linking: auto-create or match Entity (org/person) from extracted data and link via DocumentEntity
- Replace the PendingReview approval workflow with DMS Document status flow: uploaded documents start as "draft", user reviews and activates to "active"
- Add a review queue endpoint (`GET /api/v2/upload/queue`) that lists draft documents pending review, with approve/reject actions
- **BREAKING**: The legacy `/api/smart-import/*` endpoints will be deprecated (kept functional but no longer the primary path)

## Capabilities

### New Capabilities
- `unified-upload`: Single upload endpoint that handles PDF, image, and Word files, creates DMS records, and triggers async processing
- `dms-processing-pipeline`: Background processing pipeline that runs OCR, LLM analysis, auto-classification, entity linking, and thumbnail generation on uploaded documents
- `review-queue`: Draft document review workflow replacing legacy PendingReview — list pending documents, approve (draft→active), reject (delete or archive)

### Modified Capabilities

(none — Phase 1 specs are in the change directory, not yet archived to openspec/specs/)

## Impact

- **Backend**: New files `dms_processor.py`, `routers/v2_upload.py`. Reuses existing `ocr_client.py`, `ocr_agent.py`, `llm_provider.py`, `ocr_cache.py` modules (reads from them, does not modify).
- **Legacy endpoints**: `/api/smart-import/*` and `/api/materials/upload` remain functional but deprecated. No changes to legacy code.
- **Database**: No schema changes — uses DMS tables from Phase 1 as-is.
- **File storage**: New uploads go to `data/dms_files/{doc_id}/{rev_id}/` (Phase 1 convention). Thumbnails stored alongside originals.
- **External services**: Depends on OCR service and LLM provider (DeepSeek/OpenRouter/Claude) — same as current system.
- **Frontend**: Not modified in this phase. Frontend rebuild is Phase 6.

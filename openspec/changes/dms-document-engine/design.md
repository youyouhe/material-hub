## Context

MaterialHub has an existing Smart Import pipeline (`smart_import.py`) that processes uploaded files through: file type detection → PDF page extraction → OCR → LLM analysis → entity matching → PendingReview creation. This pipeline writes to legacy tables (Material, PendingReview, Company, Person). Phase 1 introduced DMS tables (Document, Revision, File, Folder, DocType, Entity). This phase bridges the gap — creating a new upload flow that produces DMS records while reusing the proven OCR/LLM infrastructure.

Key existing modules to reuse (read-only, no modifications):
- `ocr_client.py` — OCR service HTTP client
- `ocr_agent.py` — LLM-based document analysis (intelligent_extract, extract_expiry_date, create_entity_from_extraction)
- `llm_provider.py` — Multi-provider LLM client (DeepSeek, OpenRouter, Anthropic)
- `ocr_cache.py` — OCR result caching by file hash
- `page_extraction_strategy.py` — Smart page selection for PDFs
- `contract_page_analyzer.py` — Contract key page detection
- `certificate_matcher.py` — Existing certificate matching

## Goals / Non-Goals

**Goals:**
- Single upload endpoint that creates DMS Document + Revision + File in one request
- Async background processing: OCR → LLM → auto-classify → entity link → thumbnail
- Map LLM-detected material_type to DMS DocType code
- Map DocType to default Folder for auto-filing
- Replace PendingReview with Document status (draft → active) workflow
- Support PDF (multi-page with page selection), images, and Word files

**Non-Goals:**
- Modifying any legacy modules (smart_import.py, ocr_agent.py, etc.)
- Frontend changes (Phase 6)
- Full-text search indexing (Phase 3)
- Word/docx content extraction and splitting (complex, defer to later)
- Batch upload of multiple files in one request (can be done client-side with multiple calls)

## Decisions

### 1. Upload creates Document immediately, processing is async

**Decision**: The upload endpoint synchronously creates Document(status=draft) + Revision + File, then kicks off background processing. The response returns immediately with the document ID and status "processing".

**Rationale**: Users get immediate feedback (document created, shows in draft queue). Background processing updates the document as it completes each step. This matches the UX of the current smart import. Polling `GET /api/v2/documents/{id}` shows progress.

**Alternative considered**: Queue-based (Celery/RQ). Overkill for single-server deployment; Python threading is sufficient as proven by the existing implementation.

### 2. Processing pipeline as a state machine

**Decision**: Each document tracks processing state via a new `processing_status` field pattern stored in meta_json under a `_processing` key. States: `pending` → `ocr_running` → `classifying` → `linking_entities` → `completed` / `failed`.

**Rationale**: Using meta_json avoids adding columns to the DMS schema (keeps Phase 1 clean). The `_processing` key is a convention — prefixed with underscore to distinguish from user metadata. Frontend can poll document detail to show progress.

**Alternative considered**: Separate processing status table. Adds complexity without clear benefit for a single-threaded background processor.

### 3. DocType auto-detection mapping

**Decision**: Map the LLM's `material_type` output (from `ocr_agent.py`) to DMS DocType codes using a static mapping dict, similar to `migrate_to_dms.py`'s `MATERIAL_TYPE_TO_DOCTYPE`. Then map DocType to default Folder using `DOCTYPE_TO_FOLDER_PATH`.

**Rationale**: The LLM already returns reliable material_type values. A simple dict mapping is sufficient and easy to extend. Same pattern proven in the migration script.

**Mapping:**
```
LLM material_type  →  DocType code       →  Default Folder
license            →  business-license   →  /公司资质/营业执照/
iso_cert           →  iso-cert           →  /公司资质/ISO认证/
certificate        →  professional-cert  →  /人员资质/职称证书/
id_card            →  id-card           →  /人员资质/身份证件/
education          →  education-cert     →  /人员资质/学历证书/
contract           →  contract           →  /业绩材料/合同/
...
```

### 4. Entity auto-linking via existing ocr_agent

**Decision**: Reuse `create_entity_from_extraction()` from `ocr_agent.py` to get entity type and data, then create or match DMS Entity records and link via DocumentEntity.

**Rationale**: The existing entity extraction logic is proven. We just need an adapter that creates DMS Entity instead of legacy Company/Person.

### 5. Thumbnail generation approach

**Decision**: Generate thumbnails using Pillow for images and PyMuPDF for PDFs (first page render at 200px width). Store as File(type=thumbnail) in the same revision.

**Rationale**: Thumbnails are essential for the future file cabinet UI. Generating them during processing (not on-demand) avoids latency. Small fixed size (200px width) keeps storage minimal.

### 6. Review queue replaces PendingReview

**Decision**: New endpoint `GET /api/v2/upload/queue` returns documents with status "draft" ordered by created_at. Approve = PATCH status to "active". Reject = DELETE or PATCH to "archived".

**Rationale**: This uses the existing Document status machinery from Phase 1 (with transition validation). No new tables needed. The "draft" status already semantically means "pending review".

## Risks / Trade-offs

**[OCR service dependency]** → If the OCR service is down, processing fails gracefully: document stays in draft with `_processing.status = "failed"` and error message. User can retry later.

**[LLM classification accuracy]** → Auto-classification may be wrong. Mitigation: documents start as draft. The review queue lets humans verify and correct DocType/Folder before activating.

**[Thread safety]** → Background processing uses Python threads (same as legacy). SQLAlchemy sessions are created per-thread. Risk is low at current scale. If concurrency issues arise, switch to process pool in future.

**[Word file handling deferred]** → Word/docx files are stored as-is without content extraction. The legacy system extracted images from docx; this phase just stores the original. Full docx processing can be added later.

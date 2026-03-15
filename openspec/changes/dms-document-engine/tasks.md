## 1. Upload Endpoint

- [x] 1.1 Create `routers/v2_upload.py` with `POST /api/v2/upload/` endpoint — accept multipart file upload, validate MIME type (PDF, JPEG, PNG, TIFF, DOCX, DOC), return 400 for unsupported types
- [x] 1.2 Implement synchronous record creation: create DmsDocument(status=draft), Revision(version=1), DmsFile(file_type=original) and store file to `data/dms_files/{doc_id}/{rev_id}/`
- [x] 1.3 Accept optional form fields (title, folder_id, doc_type_id, notes) and set them on the document; default title to filename without extension
- [x] 1.4 Initialize `_processing` key in meta_json with `{ status: "pending" }` and kick off background thread
- [x] 1.5 Register the upload router in `main.py`

## 2. DMS Processing Pipeline

- [x] 2.1 Create `dms_processor.py` with main `process_document(document_id)` function that orchestrates the pipeline and updates `_processing` status at each step
- [x] 2.2 Implement OCR step: detect file type, for PDF extract pages using `page_extraction_strategy.py`, send to OCR via `ocr_client.py`, use `ocr_cache.py` for caching; update status to "ocr_running"
- [x] 2.3 Implement LLM classification step: pass OCR text to `ocr_agent.py`'s `intelligent_extract`, store extracted data in meta_json; update status to "classifying"
- [x] 2.4 Implement DocType auto-mapping: create `MATERIAL_TYPE_TO_DOCTYPE` dict, look up DocType by code, assign to document (skip if doc_type_id already set)
- [x] 2.5 Implement Folder auto-filing: create `DOCTYPE_TO_FOLDER_PATH` dict, look up Folder by materialized path, assign to document (skip if folder_id already set)
- [x] 2.6 Implement entity linking step: use `create_entity_from_extraction()` to get entity data, find or create DMS Entity, create DocumentEntity link with role "owner"; update status to "linking_entities"
- [x] 2.7 Implement expiry date extraction: use `extract_expiry_date()` from ocr_agent, set DmsDocument.expiry_date
- [x] 2.8 Implement PDF page extraction: render selected pages as PNG using PyMuPDF, store each as DmsFile(file_type=extracted_page)
- [x] 2.9 Implement thumbnail generation: Pillow for images (200px width), PyMuPDF first-page render for PDFs, store as DmsFile(file_type=thumbnail)
- [x] 2.10 Implement Word file handling: skip OCR/LLM steps, store original, set status to "completed" directly
- [x] 2.11 Implement error handling: catch exceptions at each step, set `_processing.status = "failed"` with error message, ensure document stays in draft

## 3. Review Queue

- [x] 3.1 Add `GET /api/v2/upload/queue` endpoint — list draft documents with pagination (offset/limit), include processing status, DocType, folder, thumbnail URL
- [x] 3.2 Add `POST /api/v2/upload/queue/{id}/approve` endpoint — validate draft status, accept optional correction fields (title, doc_type_id, folder_id, notes), transition to active
- [x] 3.3 Add `POST /api/v2/upload/queue/{id}/reject` endpoint — archive by default, delete document + files when `delete=true` query param
- [x] 3.4 Add `POST /api/v2/upload/queue/batch` endpoint — batch approve/reject with per-document results

## 4. Integration and Testing

- [x] 4.1 End-to-end test: upload a PDF via API, verify document+revision+file created, poll until processing completes, verify DocType and folder assigned
- [x] 4.2 End-to-end test: upload an image, verify thumbnail generated, verify OCR and classification
- [x] 4.3 End-to-end test: review queue — list draft docs, approve with corrections, reject with delete
- [x] 4.4 Verify existing v2 endpoints still work (no regressions from Phase 1)

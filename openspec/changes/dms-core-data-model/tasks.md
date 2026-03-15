## 1. DMS Data Models

- [x] 1.1 Create `backend/dms_models.py` with all new SQLAlchemy models: Folder, DocType, Document, Revision, File, Entity, DocumentEntity, Tag, DocumentTag. Use the field definitions from specs. Keep legacy models in `database.py` untouched for now.
- [x] 1.2 Add `init_dms_db()` function that creates all new DMS tables (calling `Base.metadata.create_all` for the new models). Integrate it into the startup sequence in `main.py` alongside the existing `init_db()`.
- [x] 1.3 Implement Folder `path` auto-computation: a utility function that builds the materialized path from parent chain, and a hook/method to recompute paths for a subtree when a folder is moved.

## 2. Seed Data

- [x] 2.1 Create `backend/seed_data.py` with a `seed_folders()` function that populates the default folder hierarchy (company qualifications with 4 subfolders, personnel qualifications with 4 subfolders, project records with 2 subfolders, bid documents with 2 subfolders) when the folders table is empty.
- [x] 2.2 Add `seed_doc_types()` function that creates the 10 default DocType records (business-license, qualification-cert, iso-cert, honor-award, id-card, education-cert, professional-cert, contract, acceptance-report, bid-document) with their metadata_schema JSON definitions, when the doc_types table is empty.
- [x] 2.3 Call `seed_folders()` and `seed_doc_types()` from the startup sequence after `init_dms_db()`.

## 3. Folder API

- [x] 3.1 Create `backend/routers/v2_folders.py` with endpoints: GET `/api/v2/folders/tree` (full tree), GET `/api/v2/folders/{id}/tree` (subtree), POST `/api/v2/folders/` (create), PATCH `/api/v2/folders/{id}` (update/move), DELETE `/api/v2/folders/{id}` (delete with non-empty check).
- [x] 3.2 Implement tree-building logic that converts flat folder rows into nested JSON with children arrays, respecting sort_order.

## 4. DocType API

- [x] 4.1 Create `backend/routers/v2_doc_types.py` with endpoints: GET `/api/v2/doc-types/` (list, with optional category filter), POST `/api/v2/doc-types/` (create custom type), PATCH `/api/v2/doc-types/{id}` (update), DELETE `/api/v2/doc-types/{id}` (delete with is_system and reference checks).

## 5. Document & Revision API

- [x] 5.1 Create `backend/routers/v2_documents.py` with document endpoints: POST `/api/v2/documents/` (create document + initial revision), GET `/api/v2/documents/` (list with filters: folder_id, doc_type_id, status, entity_id, tag_id), GET `/api/v2/documents/{id}` (detail with current_revision, entities, tags), PATCH `/api/v2/documents/{id}` (update with status transition validation), DELETE `/api/v2/documents/{id}` (cascade delete revisions, files, associations).
- [x] 5.2 Implement document status transition validation: draft→active, active→expired, active→archived, expired→archived. Reject invalid transitions with 422.
- [x] 5.3 Add revision endpoints to the documents router: GET `/api/v2/documents/{doc_id}/revisions/` (list), POST `/api/v2/documents/{doc_id}/revisions/` (create new revision, toggle is_current), GET `/api/v2/documents/{doc_id}/revisions/{rev_id}` (detail with files).

## 6. File Storage API

- [x] 6.1 Create `backend/routers/v2_files.py` with endpoints: POST `/api/v2/documents/{doc_id}/revisions/{rev_id}/files/` (upload file to revision with hash computation and duplicate check), GET `/api/v2/files/{file_id}` (serve file with path traversal protection).
- [x] 6.2 Preserve the legacy `GET /api/files/{filename}` endpoint in the existing materials router for backward compatibility.

## 7. Entity API

- [x] 7.1 Create `backend/routers/v2_entities.py` with endpoints: GET `/api/v2/entities/` (list with type filter), POST `/api/v2/entities/` (create), GET `/api/v2/entities/{id}` (detail with document count and children summary), PATCH `/api/v2/entities/{id}` (update), DELETE `/api/v2/entities/{id}` (with DocumentEntity reference check).
- [x] 7.2 Add document-entity link endpoints: POST `/api/v2/documents/{doc_id}/entities/` (link with role), DELETE `/api/v2/documents/{doc_id}/entities/{entity_id}` (unlink).

## 8. Tag API

- [x] 8.1 Create `backend/routers/v2_tags.py` with endpoints: GET `/api/v2/tags/` (list with document counts), POST `/api/v2/tags/` (create), DELETE `/api/v2/tags/{id}` (delete with cascade to DocumentTag).
- [x] 8.2 Add document-tag endpoints: POST `/api/v2/documents/{doc_id}/tags/` (add tag), DELETE `/api/v2/documents/{doc_id}/tags/{tag_id}` (remove tag).

## 9. Data Migration

- [x] 9.1 Create `backend/migrate_to_dms.py` as a standalone script. Implement database backup (copy .db file), Company→Entity(org) migration, and Person→Entity(person) migration with parent_id mapping.
- [x] 9.2 Implement Material→Document+Revision+File migration: map material_type to DocType and Folder, extract metadata from extracted_json, create Document/Revision/File records, and create DocumentEntity links from company_id/person_id.
- [x] 9.3 Implement MaterialVersion→Revision migration: for materials with version history, create additional Revision records with correct version_numbers.
- [x] 9.4 Add migration summary report output: counts of migrated/skipped/failed records per entity type, with reasons for failures.

## 10. Router Registration & Legacy Compatibility

- [x] 10.1 Register all v2 routers in `main.py` (v2_folders, v2_doc_types, v2_documents, v2_files, v2_entities, v2_tags) alongside existing routers.
- [x] 10.2 Create a legacy compatibility shim: add a `/api/materials` endpoint in the v2 layer that queries new Document/File models but returns responses in the old MaterialResponse format, preserving BidSmart integration.

## 11. Verification

- [x] 11.1 Start the application and verify seed data is created correctly (folders tree and doc types).
- [x] 11.2 Test the complete document lifecycle via API: create folder → create document in folder → upload file → create new revision → add entity link → add tag → query with filters.
- [x] 11.3 Run migration script against existing database (if data exists) and verify the migration report shows correct counts.

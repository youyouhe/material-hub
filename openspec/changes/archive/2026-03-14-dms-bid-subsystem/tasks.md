## 1. Bid Data Models

- [x] 1.1 Add `BidProject` model to `dms_models.py` with fields: id, name, bid_number, buyer, folder_id (FK), status (default "planning"), budget, deadline (Date), description, result, created_by, created_at, updated_at. Add `VALID_BID_TRANSITIONS` dict and `can_transition_to()` method.
- [x] 1.2 Add `BidRequirement` model: id, bid_project_id (FK), doc_type_id (FK, nullable), title, description, is_required (default True), sort_order, created_at, updated_at.
- [x] 1.3 Add `BidTeamMember` model: id, bid_project_id (FK), entity_id (FK), role (string), created_at. UniqueConstraint on (bid_project_id, entity_id, role).
- [x] 1.4 Add `BidDocument` model: id, bid_requirement_id (FK), document_id (FK), status (default "linked"), linked_by, linked_at, notes. UniqueConstraint on (bid_requirement_id, document_id).
- [x] 1.5 Add relationships on BidProject (requirements, team_members) with cascade delete-orphan. Add `to_dict()` methods on all four models.
- [x] 1.6 Verify all bid tables are created on `init_dms_db()` startup (DmsBase.metadata.create_all handles this automatically).

## 2. Bid Project API

- [x] 2.1 Create `routers/v2_bids.py` with `POST /api/v2/bids` — create bid project with auto-folder creation under `/投标文件/进行中/`. Protected by `require_role("editor")`. Populate `created_by` from request.
- [x] 2.2 Add `GET /api/v2/bids` — list bid projects with optional filters: status, buyer (partial match), q (name search). Include pagination (offset/limit). Include requirement summary counts (total/fulfilled/missing) per project.
- [x] 2.3 Add `GET /api/v2/bids/{bid_id}` — detail view with full metadata, team members, folder info, and requirement summary.
- [x] 2.4 Add `PATCH /api/v2/bids/{bid_id}` — update bid project fields (name, bid_number, buyer, budget, deadline, description). Protected by `require_role("editor")`.
- [x] 2.5 Add `PATCH /api/v2/bids/{bid_id}/status` — transition status with validation. On terminal status (won/lost/cancelled), move folder to "已归档". Log audit entries for status changes.
- [x] 2.6 Add `DELETE /api/v2/bids/{bid_id}` — delete bid project with cascade (requirements, team, bid-documents). Do NOT delete linked DMS documents. Protected by `require_role("editor")`.
- [x] 2.7 Add `POST /api/v2/bids/{bid_id}/team` — add team member (entity_id, role). Check uniqueness. Protected by `require_role("editor")`.
- [x] 2.8 Add `GET /api/v2/bids/{bid_id}/team` — list team members with entity details.
- [x] 2.9 Add `DELETE /api/v2/bids/{bid_id}/team/{member_id}` — remove team member. Protected by `require_role("editor")`.
- [x] 2.10 Add audit logging (`log_audit()`) to bid project create, update, delete, and status change operations.
- [x] 2.11 Register `v2_bids` router in `main.py`.

## 3. Bid Requirements API

- [x] 3.1 Create `routers/v2_bid_requirements.py` with `POST /api/v2/bids/{bid_id}/requirements` — create requirement. Protected by `require_role("editor")`.
- [x] 3.2 Add `GET /api/v2/bids/{bid_id}/requirements` — list requirements with linked documents and fulfillment status per requirement.
- [x] 3.3 Add `PATCH /api/v2/bids/{bid_id}/requirements/{req_id}` — update requirement fields. Protected by `require_role("editor")`.
- [x] 3.4 Add `DELETE /api/v2/bids/{bid_id}/requirements/{req_id}` — delete requirement and its BidDocument links. Protected by `require_role("editor")`.
- [x] 3.5 Add `POST /api/v2/bids/{bid_id}/requirements/from-category` — bulk create requirements from all doc_types in a given category. Skip existing. Protected by `require_role("editor")`.
- [x] 3.6 Add `POST /api/v2/bids/{bid_id}/requirements/{req_id}/documents` — link a DmsDocument to a requirement (creates BidDocument with status="linked"). Protected by `require_role("editor")`.
- [x] 3.7 Add `DELETE /api/v2/bids/{bid_id}/requirements/{req_id}/documents/{doc_id}` — unlink a document. Protected by `require_role("editor")`.
- [x] 3.8 Add `PATCH /api/v2/bids/{bid_id}/requirements/{req_id}/documents/{doc_id}` — update BidDocument status (to "verified"). Protected by `require_role("editor")`.
- [x] 3.9 Add `GET /api/v2/bids/{bid_id}/requirements/{req_id}/suggestions` — auto-match DMS documents by doc_type_id. Filter to active/draft documents.
- [x] 3.10 Add `GET /api/v2/bids/{bid_id}/checklist` — readiness summary: total requirements, fulfilled, missing, percentage, plus per-requirement detail. Detect deleted documents.
- [x] 3.11 Register `v2_bid_requirements` router in `main.py`.

## 4. Legacy Bridge

- [x] 4.1 Create `routers/v2_migrate.py` with `GET /api/v2/admin/migrate/status` — count legacy Company/Person/Material records vs existing Entity/DmsDocument counts. Admin-only.
- [x] 4.2 Add `POST /api/v2/admin/migrate/companies` — migrate legacy Company → Entity (entity_type="org"). Skip existing by name match. Return migration report. Admin-only.
- [x] 4.3 Add `POST /api/v2/admin/migrate/persons` — migrate legacy Person → Entity (entity_type="person") with attributes JSON. Admin-only.
- [x] 4.4 Add `POST /api/v2/admin/migrate/materials` — migrate legacy Material → DmsDocument + Revision + DmsFile. Infer doc_type from material_type. Create entity links from company_id/person_id. Skip already-migrated (by file_hash match). Admin-only.
- [x] 4.5 Register `v2_migrate` router in `main.py`.

## 5. Integration Testing

- [x] 5.1 Test bid project CRUD: create, list, get detail, update, delete.
- [x] 5.2 Test bid lifecycle: planning → active → submitted → won. Verify invalid transitions return 409.
- [x] 5.3 Test auto-folder creation and folder move on terminal status.
- [x] 5.4 Test team member management: add, list, remove, duplicate prevention.
- [x] 5.5 Test requirement CRUD: create, list with fulfillment, update, delete.
- [x] 5.6 Test document linking: link, verify, unlink, duplicate prevention.
- [x] 5.7 Test auto-match suggestions: returns matching doc_type documents, excludes archived.
- [x] 5.8 Test checklist/readiness API: correct counts, percentage, detects missing documents.
- [x] 5.9 Test bulk requirements from category.
- [x] 5.10 Test RBAC: viewer gets 403 on write operations, editor succeeds.
- [x] 5.11 Test legacy migration endpoints: companies, persons, materials, status.

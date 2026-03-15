## 1. Audit Log Data Model & Helper

- [x] 1.1 Create `AuditLog` model in `dms_models.py` with fields: id, user_id, action, target_type, target_id, target_title, details (Text/JSON), ip_address, created_at. Add index on created_at.
- [x] 1.2 Create `log_audit()` helper function in a new `dms_audit.py` module that inserts an AuditLog row within the current session transaction
- [x] 1.3 Verify audit log table is created on `init_dms_db()` startup

## 2. RBAC — User Role & Identity Propagation

- [x] 2.1 Add `role` column to legacy `User` model in `database.py` (default "editor"). Add raw SQL ALTER TABLE in `init_db()` for existing databases.
- [x] 2.2 Enhance auth middleware in `main.py` to set `request.state.user_id` and `request.state.user_role` after successful token validation
- [x] 2.3 Create `dms_auth.py` module with `require_role(min_role)` dependency and `get_current_user_id(request)` helper using role hierarchy (viewer < editor < admin)
- [x] 2.4 Update `User.to_dict()` to include `role` field

## 3. RBAC — Apply to v2 Routers

- [x] 3.1 Add `require_role("editor")` dependency to write endpoints in `v2_documents.py` (POST, PUT, DELETE)
- [x] 3.2 Add `require_role("editor")` dependency to write endpoints in `v2_folders.py`, `v2_entities.py`, `v2_tags.py`, `v2_doc_types.py`
- [x] 3.3 Add `require_role("editor")` dependency to `v2_upload.py` (upload, approve, reject, batch)
- [x] 3.4 Populate `created_by` from `request.state.user_id` in all v2 creation endpoints (documents, folders, upload)

## 4. Admin User Management API

- [x] 4.1 Create `routers/v2_admin.py` with `GET /api/v2/admin/users` (list users), protected by `require_role("admin")`
- [x] 4.2 Add `POST /api/v2/admin/users` (create user with username, password, role)
- [x] 4.3 Add `PUT /api/v2/admin/users/{id}/role` (change role, prevent self-demotion)
- [x] 4.4 Add `PUT /api/v2/admin/users/{id}/password` (reset password)
- [x] 4.5 Register `v2_admin` router in `main.py`

## 5. Document Locking

- [x] 5.1 Add `locked_by` and `locked_at` columns to `DmsDocument` model. Add raw SQL ALTER TABLE for existing databases.
- [x] 5.2 Add `POST /api/v2/documents/{id}/lock` endpoint (acquire/renew lock, 409 if locked by another)
- [x] 5.3 Add `POST /api/v2/documents/{id}/unlock` endpoint (release lock, admin force-unlock)
- [x] 5.4 Add lock check to `PUT /api/v2/documents/{id}` — reject if locked by another user
- [x] 5.5 Include lock status (locked_by, locked_at, is_locked) in document API responses

## 6. Audit Log API & Integration

- [x] 6.1 Create `routers/v2_audit.py` with `GET /api/v2/audit/logs` — query with filters (document_id, user_id, action, target_type, date_from, date_to), pagination, sorted by created_at desc
- [x] 6.2 Add `log_audit()` calls to `v2_documents.py` (create, update, delete, status change)
- [x] 6.3 Add `log_audit()` calls to `v2_upload.py` (approve, reject)
- [x] 6.4 Add `log_audit()` calls to `v2_files.py` (download)
- [x] 6.5 Add `log_audit()` calls to document lock/unlock operations
- [x] 6.6 Register `v2_audit` router in `main.py`

## 7. Integration Testing

- [x] 7.1 Test RBAC: verify viewer gets 403 on write, editor succeeds, admin can access admin endpoints
- [x] 7.2 Test audit log: create/update/delete document, verify audit entries via query API
- [x] 7.3 Test document locking: lock, renew, conflict (409), unlock, admin force-unlock, expired lock
- [x] 7.4 Test admin user management: create user, change role, reset password, prevent self-demotion
- [x] 7.5 Regression test: verify existing v2 endpoints still work with the new middleware changes

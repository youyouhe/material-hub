## Why

MaterialHub's DMS currently has no access control beyond login authentication — any authenticated user can view, edit, or delete any document. There is also no audit trail of who did what, making it impossible to track changes or investigate issues. As the system moves toward production use with multiple users, we need role-based permissions, operation logging, and basic document workflow controls.

## What Changes

- **Audit log**: New `dms_audit_log` table recording all document operations (create, update, delete, status change, download, approve, reject) with user ID, timestamp, action type, and before/after snapshots
- **Role-based access control (RBAC)**: Add `role` column to legacy `User` model (admin/editor/viewer). Admin can do everything; editor can CRUD documents; viewer is read-only
- **User identity propagation**: Extract current user from auth middleware and pass to v2 endpoints via `Request.state.user`, populate `created_by` fields on all DMS models
- **Document locking**: Optional advisory lock on documents being edited — `locked_by` / `locked_at` fields on DmsDocument, with auto-expiry after 30 minutes
- **Audit log API**: Query endpoints for viewing operation history filtered by document, user, action type, and date range
- **Admin endpoints**: User management (list users, change roles, reset passwords) restricted to admin role

## Capabilities

### New Capabilities
- `audit-log`: Operation audit trail — records all DMS actions with user identity, action type, target document, and change details. Query API for filtering and reviewing history.
- `rbac`: Role-based access control — user roles (admin/editor/viewer), permission checking middleware, role-restricted endpoint access, user management admin API.
- `document-locking`: Advisory document locks — prevent concurrent editing conflicts with lock/unlock/force-unlock operations and automatic expiry.

### Modified Capabilities
<!-- No existing specs to modify — this is all new capability -->

## Impact

- **Database**: New `dms_audit_log` table in DMS schema. `role` column added to legacy `users` table. `locked_by`/`locked_at` columns added to `dms_documents`.
- **Auth middleware**: Enhanced to inject `request.state.user` for downstream use by all v2 endpoints.
- **All v2 routers**: Updated to check user permissions before operations and log actions to audit trail. Write operations (POST/PUT/DELETE) require editor+ role; read operations open to all authenticated users.
- **API**: New endpoints under `/api/v2/audit/`, `/api/v2/admin/users/`, and lock/unlock on `/api/v2/documents/{id}/lock`.
- **Dependencies**: No new external dependencies — uses existing SQLAlchemy and FastAPI infrastructure.

## Context

MaterialHub DMS (Phase 1-3) has a working document engine with upload, processing, search, and expiry monitoring. Authentication exists via the legacy `User` + `SessionToken` tables, but there is no authorization — every logged-in user has full access to all operations. There is no audit trail of who performed what action.

The system currently has a single admin user (`admin`). The `created_by` field exists on DMS models but is never populated. The auth middleware validates tokens but does not inject user identity into the request for downstream use.

## Goals / Non-Goals

**Goals:**
- Record all significant DMS operations in an audit log with user identity
- Implement three-tier RBAC (admin / editor / viewer) on all v2 endpoints
- Propagate authenticated user identity to all v2 endpoint handlers
- Provide advisory document locking to prevent concurrent edit conflicts
- Admin API for user management (list, create, change role, reset password)

**Non-Goals:**
- Fine-grained per-folder or per-document permissions (too complex for current needs)
- Workflow engine with multi-step approval chains (future phase if needed)
- SSO / OAuth / LDAP integration (single-tenant local deployment)
- File-level encryption or DRM

## Decisions

### 1. Role storage: column on existing `users` table vs. separate role table

**Decision**: Add `role` column directly to `users` table with default `"editor"`.

**Rationale**: Three fixed roles don't warrant a separate table. A simple string column is easy to query and migrate. If granular permissions are needed later, a join table can be added.

**Alternatives considered**:
- Separate `user_roles` table: Over-engineered for 3 roles, adds join complexity
- Bitmask permissions: Hard to read, error-prone, unnecessary

### 2. Audit log: separate DMS table vs. application-level logging

**Decision**: New `dms_audit_log` table in DMS schema (via `DmsBase`).

**Rationale**: Structured queryable data is essential for audit trails. Application logs are hard to search and easy to lose. The audit table supports the query API directly.

**Schema**:
```
dms_audit_log:
  id, user_id, action (create/update/delete/status_change/download/approve/reject/lock/unlock),
  target_type (document/folder/entity/tag), target_id, target_title,
  details (JSON — before/after snapshots, change description),
  ip_address, created_at
```

### 3. User identity injection: middleware vs. dependency injection

**Decision**: Enhance existing auth middleware to set `request.state.user_id` and `request.state.user_role`, then use a FastAPI dependency `get_current_user()` in endpoints that need full user object.

**Rationale**: Middleware already validates tokens. Adding user info to `request.state` is minimal overhead. Endpoints that need the full User object can use a dependency. This avoids re-querying the session token in every endpoint.

### 4. Permission checking: decorator vs. dependency

**Decision**: FastAPI dependency functions — `require_role("admin")`, `require_role("editor")`.

**Rationale**: Dependencies are idiomatic FastAPI, composable, and testable. They integrate with OpenAPI schema for documentation.

**Implementation**:
```python
def require_role(min_role: str):
    ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "admin": 2}
    async def checker(request: Request):
        user_role = getattr(request.state, "user_role", None)
        if not user_role or ROLE_HIERARCHY.get(user_role, -1) < ROLE_HIERARCHY[min_role]:
            raise HTTPException(403, "Insufficient permissions")
    return Depends(checker)
```

### 5. Document locking: database columns vs. separate table

**Decision**: Add `locked_by` (Integer, nullable) and `locked_at` (DateTime, nullable) columns to `dms_documents`.

**Rationale**: Advisory locks are simple — only one lock per document at a time. Two columns on the document itself avoid join overhead. Auto-expiry is checked at query time (lock older than 30 minutes is considered expired).

### 6. Audit log write strategy: synchronous vs. async

**Decision**: Synchronous writes within the same DB transaction.

**Rationale**: Audit records are small, SQLite writes are fast, and we need guaranteed consistency — if an operation succeeds, its audit record must exist. Async would add complexity and risk lost audit entries.

## Risks / Trade-offs

- **SQLite ALTER TABLE for `users.role`**: Legacy `users` table uses the old `Base`. Adding a column requires either SQLAlchemy migration or raw SQL `ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'editor'`. → Mitigation: Use raw SQL ALTER in init, which SQLite supports for adding nullable/default columns.

- **SQLite ALTER TABLE for `dms_documents` lock columns**: Same approach as above — `ALTER TABLE dms_documents ADD COLUMN locked_by INTEGER` etc. → Mitigation: Raw SQL with IF NOT EXISTS check via pragma.

- **Audit log table growth**: Every operation creates a row. → Mitigation: Add index on `created_at` for time-range queries. Future: optional cleanup of old entries (not in this phase).

- **Middleware overhead**: Looking up user role on every request adds one field read. → Mitigation: Role is already on the User object fetched during session validation; no extra query needed.

- **Backward compatibility**: Existing frontend sends no role info. → Mitigation: Default role is `editor`, so current admin user keeps full access. New users created via admin API get explicit role assignment.

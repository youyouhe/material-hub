## ADDED Requirements

### Requirement: User role field
The system SHALL add a `role` column to the `users` table with allowed values: admin, editor, viewer. The default value SHALL be "editor". Existing users without a role SHALL be treated as "editor".

#### Scenario: Existing user gets default role
- **WHEN** the database is initialized and the `users` table has no `role` column
- **THEN** the system SHALL add the column with default value "editor" via ALTER TABLE

#### Scenario: Admin user role preserved
- **WHEN** an admin explicitly sets a user's role to "admin"
- **THEN** the user's role SHALL persist as "admin" across server restarts

### Requirement: User identity propagation
The system SHALL inject `request.state.user_id` and `request.state.user_role` in the auth middleware for all authenticated requests. All v2 endpoints SHALL have access to the current user's identity.

#### Scenario: Authenticated request carries user identity
- **WHEN** an authenticated user makes any request to `/api/v2/*`
- **THEN** `request.state.user_id` SHALL contain the user's ID and `request.state.user_role` SHALL contain the user's role

#### Scenario: Unauthenticated request has no user identity
- **WHEN** a request to an exempt path (e.g., `/health`) is made
- **THEN** `request.state` SHALL NOT have `user_id` or `user_role` set

### Requirement: Role-based endpoint protection
The system SHALL enforce role-based access on all v2 endpoints using a role hierarchy: admin > editor > viewer. Read operations (GET) SHALL require viewer or above. Write operations (POST, PUT, DELETE) SHALL require editor or above. Admin-only endpoints SHALL require admin role.

#### Scenario: Viewer can read documents
- **WHEN** a user with role "viewer" calls `GET /api/v2/documents`
- **THEN** the request SHALL succeed with 200

#### Scenario: Viewer cannot create documents
- **WHEN** a user with role "viewer" calls `POST /api/v2/documents`
- **THEN** the request SHALL be rejected with 403 "Insufficient permissions"

#### Scenario: Editor can create and update documents
- **WHEN** a user with role "editor" calls `POST /api/v2/documents` or `PUT /api/v2/documents/{id}`
- **THEN** the request SHALL succeed

#### Scenario: Editor cannot manage users
- **WHEN** a user with role "editor" calls `GET /api/v2/admin/users`
- **THEN** the request SHALL be rejected with 403

### Requirement: Role checking dependency
The system SHALL provide a `require_role(min_role)` FastAPI dependency that checks the current user's role against a minimum required role using the hierarchy viewer < editor < admin.

#### Scenario: Role check passes
- **WHEN** `require_role("editor")` is used and the user has role "admin"
- **THEN** the dependency SHALL pass (admin >= editor)

#### Scenario: Role check fails
- **WHEN** `require_role("editor")` is used and the user has role "viewer"
- **THEN** the dependency SHALL raise HTTPException with status 403

### Requirement: Admin user management API
The system SHALL provide admin-only endpoints for user management:
- `GET /api/v2/admin/users` — list all users with roles
- `POST /api/v2/admin/users` — create new user with username, password, role
- `PUT /api/v2/admin/users/{id}/role` — change a user's role
- `PUT /api/v2/admin/users/{id}/password` — reset a user's password

#### Scenario: Admin lists users
- **WHEN** an admin calls `GET /api/v2/admin/users`
- **THEN** the system SHALL return a list of all users with id, username, role, created_at, last_login

#### Scenario: Admin creates user
- **WHEN** an admin calls `POST /api/v2/admin/users` with username, password, role
- **THEN** a new user SHALL be created with the specified role and a hashed password

#### Scenario: Admin changes user role
- **WHEN** an admin calls `PUT /api/v2/admin/users/{id}/role` with role="viewer"
- **THEN** the target user's role SHALL be updated to "viewer"

#### Scenario: Admin resets user password
- **WHEN** an admin calls `PUT /api/v2/admin/users/{id}/password` with new_password
- **THEN** the target user's password_hash SHALL be updated

#### Scenario: Prevent self-demotion from admin
- **WHEN** an admin tries to change their own role to non-admin
- **THEN** the request SHALL be rejected with 400 "Cannot demote yourself"

### Requirement: created_by population
All v2 endpoints that create DMS records (documents, folders, entities, tags, revisions) SHALL populate the `created_by` field with the current user's ID from `request.state.user_id`.

#### Scenario: Document created with user ID
- **WHEN** an editor creates a document via `POST /api/v2/documents`
- **THEN** the document's `created_by` field SHALL be set to the editor's user ID

#### Scenario: Upload sets created_by
- **WHEN** a user uploads a file via `POST /api/v2/upload/`
- **THEN** the created document's `created_by` SHALL be the uploader's user ID

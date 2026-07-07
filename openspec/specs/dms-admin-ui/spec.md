## ADDED Requirements

### Requirement: User management page
The admin users page SHALL display a list of users from `GET /api/v2/admin/users`. Each row SHALL show username, role, and status. Admins SHALL be able to create users, update roles, and toggle active/inactive status.

#### Scenario: User list loads
- **WHEN** admin navigates to the users page
- **THEN** the page fetches from `/api/v2/admin/users` and displays all users in a table

#### Scenario: Create user
- **WHEN** admin fills in the create user form (username, password, role) and submits
- **THEN** the system calls `POST /api/v2/admin/users` and the new user appears in the list

#### Scenario: Update user role
- **WHEN** admin changes a user's role via dropdown and confirms
- **THEN** the system calls `PATCH /api/v2/admin/users/{id}` with the new role

#### Scenario: Non-admin cannot access
- **WHEN** a non-admin user attempts to navigate to the admin users page
- **THEN** the page is not accessible (nav item hidden, page component not rendered)

### Requirement: Audit log viewer
The admin audit page SHALL display audit log entries from `GET /api/v2/audit/logs`. Each row SHALL show timestamp, user, action, resource type, resource name, and details. The page SHALL support filtering by action type, resource type, and date range, with pagination.

#### Scenario: Audit log loads with pagination
- **WHEN** admin navigates to the audit log page
- **THEN** the page fetches from `/api/v2/audit/logs` with default pagination and displays log entries in reverse chronological order

#### Scenario: Filter by action type
- **WHEN** admin selects an action type filter (create, update, delete, status_change, etc.)
- **THEN** the log list re-fetches with the action filter applied

#### Scenario: Filter by resource type
- **WHEN** admin selects a resource type filter (document, bid_project, entity, etc.)
- **THEN** the log list re-fetches with the resource_type filter applied

### Requirement: Migration dashboard
The admin section SHALL include a migration status page showing legacy-to-DMS migration progress from `GET /api/v2/admin/migrate/status`. Admins SHALL be able to trigger migration for companies, persons, and materials via the corresponding POST endpoints.

#### Scenario: Migration status display
- **WHEN** admin navigates to the migration page
- **THEN** the page shows legacy vs migrated counts for companies, persons, and materials

#### Scenario: Trigger migration
- **WHEN** admin clicks "Migrate Companies" button
- **THEN** the system calls `POST /api/v2/admin/migrate/companies` and displays the result (created, skipped, total)

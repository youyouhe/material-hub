## ADDED Requirements

### Requirement: Audit log data model
The system SHALL store audit log entries in a `dms_audit_log` table with fields: id, user_id, action, target_type, target_id, target_title, details (JSON), ip_address, created_at. The `action` field SHALL accept values: create, update, delete, status_change, download, approve, reject, lock, unlock. The `target_type` field SHALL accept values: document, folder, entity, tag.

#### Scenario: Audit log table creation
- **WHEN** the DMS database is initialized
- **THEN** the `dms_audit_log` table SHALL be created with all required columns and an index on `created_at`

### Requirement: Automatic audit logging on document operations
The system SHALL automatically create an audit log entry whenever a document is created, updated, deleted, or has its status changed. The entry SHALL include the user who performed the action, the action type, the target document ID and title, and relevant change details in JSON format.

#### Scenario: Document creation logged
- **WHEN** a user creates a new document via `POST /api/v2/documents`
- **THEN** an audit entry with action="create" SHALL be recorded with the user's ID and the new document's ID and title

#### Scenario: Document status change logged
- **WHEN** a user changes a document's status (e.g., approve, reject, archive)
- **THEN** an audit entry SHALL be recorded with the old and new status in the details JSON

#### Scenario: Document deletion logged
- **WHEN** a user deletes a document via `DELETE /api/v2/documents/{id}`
- **THEN** an audit entry with action="delete" SHALL be recorded with the document's title preserved in target_title

### Requirement: Automatic audit logging on upload review actions
The system SHALL create audit log entries when documents are approved or rejected through the upload review queue.

#### Scenario: Upload approval logged
- **WHEN** a user approves a document via `POST /api/v2/upload/approve`
- **THEN** an audit entry with action="approve" SHALL be recorded

#### Scenario: Upload rejection logged
- **WHEN** a user rejects a document via `POST /api/v2/upload/reject`
- **THEN** an audit entry with action="reject" SHALL be recorded

### Requirement: File download audit logging
The system SHALL create an audit log entry when a user downloads a file via the files endpoint.

#### Scenario: File download logged
- **WHEN** a user downloads a file via `GET /api/v2/files/{id}`
- **THEN** an audit entry with action="download" SHALL be recorded with the file's parent document as the target

### Requirement: Audit log query API
The system SHALL provide `GET /api/v2/audit/logs` to query audit log entries with optional filters: document_id, user_id, action, target_type, date_from, date_to. Results SHALL be paginated and sorted by created_at descending.

#### Scenario: Query audit logs by document
- **WHEN** a user calls `GET /api/v2/audit/logs?document_id=5`
- **THEN** the system SHALL return all audit entries where target_type="document" and target_id=5, paginated

#### Scenario: Query audit logs by date range
- **WHEN** a user calls `GET /api/v2/audit/logs?date_from=2026-03-01&date_to=2026-03-14`
- **THEN** the system SHALL return all audit entries within that date range

#### Scenario: Query audit logs by action type
- **WHEN** a user calls `GET /api/v2/audit/logs?action=delete`
- **THEN** the system SHALL return only audit entries with action="delete"

### Requirement: Audit log helper function
The system SHALL provide a reusable `log_audit(session, user_id, action, target_type, target_id, target_title, details, ip_address)` function that all v2 routers can call to record audit entries.

#### Scenario: Helper function creates audit entry
- **WHEN** any router calls `log_audit()` with required parameters
- **THEN** a new row SHALL be inserted into `dms_audit_log` within the current transaction

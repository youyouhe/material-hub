## ADDED Requirements

### Requirement: Document lock fields
The system SHALL add `locked_by` (Integer, nullable) and `locked_at` (DateTime, nullable) columns to the `dms_documents` table. A document is considered locked when `locked_by` is not null and `locked_at` is within the last 30 minutes.

#### Scenario: Lock columns added to documents table
- **WHEN** the DMS database is initialized
- **THEN** the `dms_documents` table SHALL have `locked_by` and `locked_at` columns (added via ALTER TABLE if not present)

#### Scenario: Expired lock treated as unlocked
- **WHEN** a document has `locked_by` set but `locked_at` is older than 30 minutes
- **THEN** the system SHALL treat the document as unlocked

### Requirement: Lock document endpoint
The system SHALL provide `POST /api/v2/documents/{id}/lock` to acquire an advisory lock on a document. Only editors and admins can lock documents.

#### Scenario: Lock available document
- **WHEN** an editor calls `POST /api/v2/documents/{id}/lock` on an unlocked document
- **THEN** `locked_by` SHALL be set to the user's ID, `locked_at` to current time, and response SHALL be 200 with lock details

#### Scenario: Lock already-locked document by same user
- **WHEN** the lock holder calls `POST /api/v2/documents/{id}/lock` again
- **THEN** `locked_at` SHALL be refreshed (lock renewal) and response SHALL be 200

#### Scenario: Lock already-locked document by different user
- **WHEN** a different user calls `POST /api/v2/documents/{id}/lock` on a document locked by another user (within 30 minutes)
- **THEN** the request SHALL be rejected with 409 "Document is locked by another user"

### Requirement: Unlock document endpoint
The system SHALL provide `POST /api/v2/documents/{id}/unlock` to release a lock. The lock holder or an admin can unlock.

#### Scenario: Lock holder unlocks
- **WHEN** the lock holder calls `POST /api/v2/documents/{id}/unlock`
- **THEN** `locked_by` and `locked_at` SHALL be set to null, response SHALL be 200

#### Scenario: Admin force-unlocks
- **WHEN** an admin calls `POST /api/v2/documents/{id}/unlock` on a document locked by another user
- **THEN** the lock SHALL be released and an audit entry with action="unlock" SHALL be recorded

#### Scenario: Non-holder non-admin tries to unlock
- **WHEN** a non-admin user who is not the lock holder calls `POST /api/v2/documents/{id}/unlock`
- **THEN** the request SHALL be rejected with 403

### Requirement: Lock check on document updates
The system SHALL check document lock status before allowing updates. If a document is locked by another user, update operations SHALL be rejected.

#### Scenario: Update locked document by lock holder
- **WHEN** the lock holder calls `PUT /api/v2/documents/{id}` on their locked document
- **THEN** the update SHALL proceed normally

#### Scenario: Update locked document by different user
- **WHEN** a non-holder user calls `PUT /api/v2/documents/{id}` on a locked document
- **THEN** the request SHALL be rejected with 409 "Document is locked by another user"

#### Scenario: Update unlocked document
- **WHEN** any editor calls `PUT /api/v2/documents/{id}` on an unlocked document
- **THEN** the update SHALL proceed normally (no lock required)

### Requirement: Lock status in document response
The system SHALL include lock information in document API responses: `lock` object with `locked_by`, `locked_by_username`, `locked_at`, `is_locked` (boolean, considering 30-minute expiry).

#### Scenario: Locked document shows lock info
- **WHEN** `GET /api/v2/documents/{id}` is called for a locked document
- **THEN** the response SHALL include `lock: {locked_by: 1, locked_by_username: "admin", locked_at: "...", is_locked: true}`

#### Scenario: Unlocked document shows null lock
- **WHEN** `GET /api/v2/documents/{id}` is called for an unlocked document
- **THEN** the response SHALL include `lock: {locked_by: null, locked_at: null, is_locked: false}`

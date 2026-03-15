## ADDED Requirements

### Requirement: Expiry summary endpoint
The system SHALL provide `GET /api/v2/expiry/summary` returning aggregated expiry data: count of documents expiring within 30 days, within 60 days, within 90 days, already expired (active status with past expiry_date), and per-DocType breakdown of expiring/expired counts.

#### Scenario: Summary with mixed expiry states
- **WHEN** there are 5 documents expiring within 30 days, 3 within 60 days, and 2 already expired
- **THEN** the response includes `{"expiring_30d": 5, "expiring_60d": 8, "expiring_90d": N, "expired": 2, "by_doc_type": [...]}`

#### Scenario: No expiring documents
- **WHEN** no documents have expiry dates set or all are far in the future
- **THEN** all counts are 0

### Requirement: Expiring-soon document list
The system SHALL provide `GET /api/v2/expiry/expiring` with optional `days` parameter (default 30) that returns documents with expiry_date between today and today + N days, ordered by expiry_date ascending (soonest first). The endpoint SHALL support pagination via `limit` and `offset`.

#### Scenario: Documents expiring within 30 days
- **WHEN** `GET /api/v2/expiry/expiring?days=30`
- **THEN** only documents with expiry_date within the next 30 days are returned
- **AND** results are ordered by soonest expiry first

#### Scenario: Custom expiry window
- **WHEN** `GET /api/v2/expiry/expiring?days=90`
- **THEN** documents expiring within 90 days are returned

### Requirement: Expired document list
The system SHALL provide `GET /api/v2/expiry/expired` that returns documents with expiry_date in the past that are still in "active" status (not yet archived). Results SHALL be ordered by expiry_date ascending (longest-expired first). The endpoint SHALL support pagination via `limit` and `offset`.

#### Scenario: List expired but still active documents
- **WHEN** 3 documents have past expiry dates and active status
- **THEN** all 3 are returned ordered by expiry date (oldest first)

#### Scenario: No expired active documents
- **WHEN** all expired documents have been archived
- **THEN** an empty result set is returned

### Requirement: Auto-update expired document status
The system SHALL provide `POST /api/v2/expiry/update-status` that scans all active documents with past expiry_date and transitions them to "expired" status. The endpoint SHALL return the count of documents updated.

#### Scenario: Batch update expired documents
- **WHEN** `POST /api/v2/expiry/update-status` is called
- **AND** 5 active documents have past expiry dates
- **THEN** all 5 are transitioned to "expired" status
- **AND** the response includes `{"updated_count": 5}`

#### Scenario: No documents to update
- **WHEN** no active documents have past expiry dates
- **THEN** `{"updated_count": 0}`

### Requirement: Expiry endpoints require authentication
The system SHALL require a valid authentication token for all expiry monitoring endpoints. Unauthenticated requests SHALL receive HTTP 401.

#### Scenario: Unauthenticated expiry access
- **WHEN** `GET /api/v2/expiry/summary` without auth token
- **THEN** HTTP 401 is returned

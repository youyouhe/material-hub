## ADDED Requirements

### Requirement: Review queue lists draft documents
The system SHALL provide `GET /api/v2/upload/queue` that returns documents with status "draft" ordered by created_at descending. The response SHALL include document ID, title, DocType, folder, processing status, created_at, and thumbnail URL. The endpoint SHALL support pagination via `offset` and `limit` query parameters (default limit=50).

#### Scenario: List pending documents
- **WHEN** there are 3 documents in "draft" status
- **THEN** `GET /api/v2/upload/queue` returns all 3 documents ordered by newest first
- **AND** each document includes its processing status from meta_json._processing

#### Scenario: Empty queue
- **WHEN** there are no documents in "draft" status
- **THEN** `GET /api/v2/upload/queue` returns an empty list with total=0

#### Scenario: Pagination
- **WHEN** there are 100 draft documents and `offset=10&limit=20` is provided
- **THEN** the response contains documents 11-30 with total=100

### Requirement: Approve document transitions draft to active
The system SHALL provide `POST /api/v2/upload/queue/{id}/approve` that transitions a document from "draft" to "active" status. The endpoint SHALL use the existing status transition validation from Phase 1. Approving a document that is not in "draft" status SHALL return HTTP 409.

#### Scenario: Approve a draft document
- **WHEN** `POST /api/v2/upload/queue/{id}/approve` is called for a draft document
- **THEN** the document status changes to "active"
- **AND** the response returns the updated document

#### Scenario: Approve a non-draft document
- **WHEN** `POST /api/v2/upload/queue/{id}/approve` is called for a document with status "active"
- **THEN** the system returns HTTP 409 with error "Invalid status transition"

#### Scenario: Approve non-existent document
- **WHEN** `POST /api/v2/upload/queue/{id}/approve` is called with an invalid ID
- **THEN** the system returns HTTP 404

### Requirement: Reject document archives or deletes it
The system SHALL provide `POST /api/v2/upload/queue/{id}/reject` that transitions a document from "draft" to "archived" status. An optional `delete` query parameter (boolean, default false) SHALL permanently delete the document and its associated files instead.

#### Scenario: Reject a draft document (archive)
- **WHEN** `POST /api/v2/upload/queue/{id}/reject` is called without `delete` parameter
- **THEN** the document status changes to "archived"

#### Scenario: Reject a draft document (delete)
- **WHEN** `POST /api/v2/upload/queue/{id}/reject?delete=true` is called
- **THEN** the document, its revisions, files, and physical files are permanently deleted

#### Scenario: Reject a non-draft document
- **WHEN** `POST /api/v2/upload/queue/{id}/reject` is called for a non-draft document
- **THEN** the system returns HTTP 409

### Requirement: Approve with corrections
The system SHALL accept optional fields on the approve endpoint: `title`, `doc_type_id`, `folder_id`, `notes`. These fields SHALL update the document before transitioning to "active" status, allowing reviewers to correct auto-classification results.

#### Scenario: Approve with corrected DocType
- **WHEN** `POST /api/v2/upload/queue/{id}/approve` is called with `doc_type_id=3`
- **THEN** the document's doc_type is updated to ID 3
- **AND** the document status changes to "active"

#### Scenario: Approve with corrected title and folder
- **WHEN** `POST /api/v2/upload/queue/{id}/approve` is called with `title="新标题"` and `folder_id=7`
- **THEN** the document's title and folder are updated
- **AND** the document status changes to "active"

### Requirement: Batch approve and reject
The system SHALL provide `POST /api/v2/upload/queue/batch` that accepts a JSON body with `action` ("approve" or "reject") and `document_ids` (array of integers). The endpoint SHALL process each document individually and return results per document (success or error).

#### Scenario: Batch approve 5 documents
- **WHEN** `POST /api/v2/upload/queue/batch` with action="approve" and 5 document IDs
- **THEN** all 5 documents transition to "active" status
- **AND** the response includes per-document results

#### Scenario: Batch with mixed results
- **WHEN** batch approve is called with 3 draft and 1 active document
- **THEN** 3 documents succeed and 1 returns an error
- **AND** the response includes both successes and failures

### Requirement: Review queue requires authentication
The system SHALL require a valid authentication token for all review queue endpoints. Unauthenticated requests SHALL receive HTTP 401.

#### Scenario: Unauthenticated queue access
- **WHEN** `GET /api/v2/upload/queue` is called without an auth token
- **THEN** the system returns HTTP 401

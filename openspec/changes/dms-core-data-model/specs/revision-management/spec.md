## ADDED Requirements

### Requirement: Revision data model
The system SHALL store revisions with the following fields: id (auto-increment), document_id (required reference to Document), version_number (integer, auto-incrementing per document), is_current (boolean, default true), change_note (nullable string), created_by (nullable user reference), created_at (datetime).

#### Scenario: First revision created with document
- **WHEN** a new document is created
- **THEN** the system automatically creates a revision with version_number=1 and is_current=true

#### Scenario: New revision marks previous as non-current
- **WHEN** a new revision is added to a document that already has revisions
- **THEN** the system sets is_current=false on all previous revisions and is_current=true on the new revision, with version_number incremented by 1

### Requirement: Revision CRUD operations
The system SHALL provide API endpoints to manage revisions within a document.

#### Scenario: List revisions for a document
- **WHEN** a GET request is made to `/api/v2/documents/{doc_id}/revisions/`
- **THEN** the system returns all revisions for that document ordered by version_number descending

#### Scenario: Create new revision
- **WHEN** a POST request is made to `/api/v2/documents/{doc_id}/revisions/` with an optional change_note
- **THEN** the system creates a new revision with incremented version_number, marks it as current, and marks all previous revisions as non-current

#### Scenario: Get specific revision
- **WHEN** a GET request is made to `/api/v2/documents/{doc_id}/revisions/{rev_id}`
- **THEN** the system returns the revision with its associated files

### Requirement: Current revision access
The system SHALL provide convenient access to the current (latest) revision of a document.

#### Scenario: Get current revision via document endpoint
- **WHEN** a GET request is made to `/api/v2/documents/{id}`
- **THEN** the response includes a `current_revision` field with the latest revision and its files

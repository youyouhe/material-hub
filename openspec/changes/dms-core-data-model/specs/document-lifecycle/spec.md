## ADDED Requirements

### Requirement: Document data model
The system SHALL store documents with the following fields: id (auto-increment), folder_id (required reference to Folder), doc_type_id (required reference to DocType), title (string, required), description (nullable string), status (string enum: draft/active/expired/archived, default draft), metadata (JSON, nullable — stores type-specific fields per DocType.metadata_schema), expiry_date (nullable date), created_by (nullable user reference), created_at (datetime), updated_at (datetime).

#### Scenario: Create document with metadata
- **WHEN** a document is created with doc_type_id referencing a DocType whose metadata_schema defines fields like cert_number and issuing_authority
- **THEN** the document is saved with the metadata JSON containing those field values

#### Scenario: Document without metadata
- **WHEN** a document is created with no metadata provided
- **THEN** the document is saved with metadata as null or empty JSON object

### Requirement: Document CRUD operations
The system SHALL provide API endpoints to create, read, update, and delete documents.

#### Scenario: Create document
- **WHEN** a POST request is made to `/api/v2/documents/` with title, folder_id, and doc_type_id
- **THEN** the system creates the document with status "draft" and returns it

#### Scenario: Get document by ID
- **WHEN** a GET request is made to `/api/v2/documents/{id}`
- **THEN** the system returns the document with its current revision, associated entities, tags, folder info, and doc type info

#### Scenario: Update document
- **WHEN** a PATCH request is made to `/api/v2/documents/{id}` with updated fields
- **THEN** the system updates only the provided fields and returns the updated document

#### Scenario: Delete document
- **WHEN** a DELETE request is made to `/api/v2/documents/{id}`
- **THEN** the system deletes the document, all its revisions, all associated files (both database records and physical files), and all entity/tag associations

### Requirement: Document status transitions
The system SHALL enforce valid status transitions for documents.

#### Scenario: Valid transition from draft to active
- **WHEN** a document in "draft" status is updated to "active"
- **THEN** the system accepts the transition and updates the status

#### Scenario: Valid transition from active to expired
- **WHEN** a document in "active" status is updated to "expired"
- **THEN** the system accepts the transition and updates the status

#### Scenario: Valid transition from active to archived
- **WHEN** a document in "active" status is updated to "archived"
- **THEN** the system accepts the transition and updates the status

#### Scenario: Invalid transition rejected
- **WHEN** a document in "archived" status is updated to "draft"
- **THEN** the system returns a 422 error indicating an invalid status transition

### Requirement: Document listing with filters
The system SHALL provide an API endpoint to list documents with multiple filter options.

#### Scenario: List documents by folder
- **WHEN** a GET request is made to `/api/v2/documents/?folder_id={id}`
- **THEN** the system returns all documents in that folder, ordered by updated_at descending

#### Scenario: List documents by doc type
- **WHEN** a GET request is made to `/api/v2/documents/?doc_type_id={id}`
- **THEN** the system returns all documents of that type across all folders

#### Scenario: List documents by status
- **WHEN** a GET request is made to `/api/v2/documents/?status=active`
- **THEN** the system returns only documents with active status

#### Scenario: List documents by entity
- **WHEN** a GET request is made to `/api/v2/documents/?entity_id={id}`
- **THEN** the system returns all documents linked to that entity

#### Scenario: List expired documents
- **WHEN** a GET request is made to `/api/v2/documents/?status=expired` or documents have expiry_date before today
- **THEN** the system returns documents that are expired, supporting the bid material expiry tracking use case

## ADDED Requirements

### Requirement: Tag data model
The system SHALL store tags with the following fields: id (auto-increment), name (string, required, unique), color (nullable string — hex color code for UI display), created_at (datetime).

#### Scenario: Create a tag
- **WHEN** a tag is created with name "urgent" and color "#FF0000"
- **THEN** the tag is saved and available for document association

### Requirement: DocumentTag relationship
The system SHALL store document-tag associations via a join table with fields: document_id (reference to Document), tag_id (reference to Tag), with a unique constraint on (document_id, tag_id).

#### Scenario: Tag a document
- **WHEN** a tag is associated with a document
- **THEN** the DocumentTag record is created

#### Scenario: Duplicate tag on same document prevented
- **WHEN** a tag that is already associated with a document is associated again
- **THEN** the system returns a 409 Conflict or silently ignores the duplicate

### Requirement: Tag CRUD operations
The system SHALL provide API endpoints to manage tags.

#### Scenario: List all tags
- **WHEN** a GET request is made to `/api/v2/tags/`
- **THEN** the system returns all tags with document count for each

#### Scenario: Create tag
- **WHEN** a POST request is made to `/api/v2/tags/` with name and optional color
- **THEN** the system creates the tag and returns it

#### Scenario: Delete tag
- **WHEN** a DELETE request is made to `/api/v2/tags/{id}`
- **THEN** the system deletes the tag and all its DocumentTag associations

### Requirement: Document tagging operations
The system SHALL provide API endpoints to add/remove tags on documents.

#### Scenario: Add tag to document
- **WHEN** a POST request is made to `/api/v2/documents/{doc_id}/tags/` with tag_id
- **THEN** the system creates the association

#### Scenario: Remove tag from document
- **WHEN** a DELETE request is made to `/api/v2/documents/{doc_id}/tags/{tag_id}`
- **THEN** the system removes the association

#### Scenario: List documents by tag
- **WHEN** a GET request is made to `/api/v2/documents/?tag_id={id}`
- **THEN** the system returns all documents associated with that tag

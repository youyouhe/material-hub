## ADDED Requirements

### Requirement: Entity data model
The system SHALL store entities with the following fields: id (auto-increment), entity_type (string enum: org/person, required), name (string, required), attributes (JSON, nullable — type-specific fields), parent_id (nullable self-reference — person belongs to org), created_at (datetime), updated_at (datetime).

#### Scenario: Organization entity
- **WHEN** an entity is created with entity_type "org" and attributes containing credit_code, legal_person, and address
- **THEN** the entity is saved as an organization with those attributes

#### Scenario: Person entity linked to organization
- **WHEN** an entity is created with entity_type "person", parent_id referencing an org entity, and attributes containing id_number, education, and position
- **THEN** the entity is saved as a person belonging to that organization

### Requirement: DocumentEntity relationship
The system SHALL store document-entity associations with the following fields: id (auto-increment), document_id (required reference to Document), entity_id (required reference to Entity), role (string enum: owner/issuer/subject/related, required), created_at (datetime).

#### Scenario: Link document to owning entity
- **WHEN** a business license document is linked to a company entity with role "owner"
- **THEN** the DocumentEntity record is created, and querying documents for that entity returns this document

#### Scenario: Multiple entities per document
- **WHEN** a contract document is linked to entity A with role "owner" and entity B with role "related"
- **THEN** both DocumentEntity records are created, and the document appears in queries for either entity

### Requirement: Entity CRUD operations
The system SHALL provide API endpoints to manage entities.

#### Scenario: List entities with type filter
- **WHEN** a GET request is made to `/api/v2/entities/?type=org`
- **THEN** the system returns all organization entities

#### Scenario: Create entity
- **WHEN** a POST request is made to `/api/v2/entities/` with entity_type, name, and attributes
- **THEN** the system creates the entity and returns it

#### Scenario: Get entity with linked documents
- **WHEN** a GET request is made to `/api/v2/entities/{id}`
- **THEN** the system returns the entity including a count of linked documents and a summary of its child entities (persons under an org)

#### Scenario: Update entity
- **WHEN** a PATCH request is made to `/api/v2/entities/{id}` with updated name or attributes
- **THEN** the system updates the entity and returns the updated record

#### Scenario: Delete entity with no linked documents
- **WHEN** a DELETE request is made to `/api/v2/entities/{id}` and no DocumentEntity records reference it
- **THEN** the system deletes the entity

#### Scenario: Delete entity with linked documents rejected
- **WHEN** a DELETE request is made to `/api/v2/entities/{id}` and DocumentEntity records exist
- **THEN** the system returns a 409 Conflict error

### Requirement: Document-entity link management
The system SHALL provide API endpoints to manage document-entity associations.

#### Scenario: Link entity to document
- **WHEN** a POST request is made to `/api/v2/documents/{doc_id}/entities/` with entity_id and role
- **THEN** the system creates the DocumentEntity association

#### Scenario: Unlink entity from document
- **WHEN** a DELETE request is made to `/api/v2/documents/{doc_id}/entities/{entity_id}`
- **THEN** the system removes the DocumentEntity association

## ADDED Requirements

### Requirement: DocType data model
The system SHALL store document types with the following fields: id (auto-increment), name (string, required — display name), code (string, required, unique — kebab-case identifier), category (string, required — grouping: company/personnel/project/bid/general), metadata_schema (JSON, nullable — defines the custom fields for this document type), icon (nullable string — icon identifier for UI), description (nullable string), is_system (boolean, default false — prevents deletion of seed types), created_at (datetime), updated_at (datetime).

#### Scenario: DocType with metadata schema
- **WHEN** a DocType is created with code "business-license" and metadata_schema defining fields registration_number (string), legal_person (string), registered_capital (string), business_scope (text), issue_date (date)
- **THEN** the DocType is saved and documents of this type can store those fields in their metadata JSON

#### Scenario: DocType metadata schema format
- **WHEN** a metadata_schema is defined
- **THEN** each field entry SHALL contain at minimum: key (field identifier), type (string/text/date/number/boolean), and label (display name in Chinese)

### Requirement: DocType CRUD operations
The system SHALL provide API endpoints to manage document types.

#### Scenario: List all doc types
- **WHEN** a GET request is made to `/api/v2/doc-types/`
- **THEN** the system returns all document types grouped by category

#### Scenario: List doc types by category
- **WHEN** a GET request is made to `/api/v2/doc-types/?category=company`
- **THEN** the system returns only document types in the "company" category

#### Scenario: Create custom doc type
- **WHEN** a POST request is made to `/api/v2/doc-types/` with name, code, category, and metadata_schema
- **THEN** the system creates the DocType with is_system=false and returns it

#### Scenario: Update doc type
- **WHEN** a PATCH request is made to `/api/v2/doc-types/{id}` with updated fields
- **THEN** the system updates the DocType and returns the updated record

#### Scenario: Delete custom doc type
- **WHEN** a DELETE request is made to `/api/v2/doc-types/{id}` and is_system is false and no documents reference this type
- **THEN** the system deletes the DocType

#### Scenario: Delete system doc type rejected
- **WHEN** a DELETE request is made to `/api/v2/doc-types/{id}` and is_system is true
- **THEN** the system returns a 403 error indicating system types cannot be deleted

### Requirement: Seed default document types
The system SHALL create default document types on first startup when the doc_types table is empty.

#### Scenario: First startup seeds doc types
- **WHEN** the application starts and the doc_types table contains zero rows
- **THEN** the system creates the following seed DocTypes with is_system=true:
  - business-license (category: company) — fields: registration_number, legal_person, registered_capital, business_scope, issue_date, valid_to
  - qualification-cert (category: company) — fields: cert_number, cert_level, issuing_authority, valid_from, valid_to
  - iso-cert (category: company) — fields: cert_number, standard, scope, issuing_authority, valid_from, valid_to
  - honor-award (category: company) — fields: award_name, issuing_authority, award_date, level
  - id-card (category: personnel) — fields: id_number, gender, birth_date, address
  - education-cert (category: personnel) — fields: school, major, degree, graduation_date
  - professional-cert (category: personnel) — fields: cert_name, cert_number, cert_level, issuing_authority, valid_from, valid_to
  - contract (category: project) — fields: contract_number, party_a, party_b, contract_amount, sign_date, start_date, end_date
  - acceptance-report (category: project) — fields: project_name, acceptance_date, acceptance_result, participants
  - bid-document (category: bid) — fields: project_name, bid_number, submission_date, bid_amount, result

## ADDED Requirements

### Requirement: Legacy company to entity migration
The system SHALL provide POST /api/v2/admin/migrate/companies (admin-only) that migrates legacy Company records to DMS Entity records (entity_type="org"). If an Entity with the same name already exists, it SHALL be skipped. The endpoint SHALL return a migration report.

#### Scenario: Migrate companies
- **WHEN** POST /api/v2/admin/migrate/companies is called and there are 5 legacy companies, 2 already exist as entities
- **THEN** 3 new Entity records are created, and the response reports created=3, skipped=2, total=5

### Requirement: Legacy person to entity migration
The system SHALL provide POST /api/v2/admin/migrate/persons (admin-only) that migrates legacy Person records to DMS Entity records (entity_type="person"). Attributes like education, position, and id_number SHALL be stored in the Entity.attributes JSON.

#### Scenario: Migrate persons with attributes
- **WHEN** POST /api/v2/admin/migrate/persons is called with legacy persons having education and position fields
- **THEN** Entity records are created with attributes JSON containing those fields

### Requirement: Legacy material to document migration
The system SHALL provide POST /api/v2/admin/migrate/materials (admin-only) that migrates legacy Material records to DMS Documents. Each Material becomes a DmsDocument with a single Revision and File. The doc_type SHALL be inferred from material_type. Entity links SHALL be created based on company_id/person_id.

#### Scenario: Migrate material with company link
- **WHEN** a legacy Material has company_id=1, material_type="license", and an image file
- **THEN** a DmsDocument is created with doc_type matching "business-license", an entity link to the corresponding Entity (migrated from Company id=1), and the image file is registered as a DmsFile

#### Scenario: Skip already-migrated materials
- **WHEN** migration is run twice
- **THEN** the second run skips materials that have already been migrated (tracked by a meta_json flag or hash match)

### Requirement: Migration status endpoint
The system SHALL provide GET /api/v2/admin/migrate/status (admin-only) that returns counts of legacy records vs migrated records for companies, persons, and materials.

#### Scenario: Check migration status
- **WHEN** GET /api/v2/admin/migrate/status
- **THEN** response includes {companies: {legacy: 5, migrated: 3}, persons: {legacy: 10, migrated: 8}, materials: {legacy: 50, migrated: 45}}

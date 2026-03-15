## ADDED Requirements

### Requirement: Migration script
The system SHALL provide a standalone Python migration script (`migrate_to_dms.py`) that transforms data from the legacy schema to the new DMS schema.

#### Scenario: Run migration
- **WHEN** the migration script is executed against a database containing legacy data
- **THEN** the script creates new DMS tables (if not exists), migrates all data, and outputs a summary report

#### Scenario: Run migration on empty database
- **WHEN** the migration script is executed against a database with no legacy data
- **THEN** the script completes successfully with zero records migrated

### Requirement: Company to Entity migration
The system SHALL migrate all Company records to Entity records with entity_type "org".

#### Scenario: Company migrated to org entity
- **WHEN** a Company record exists with name "XX科技有限公司", legal_person "张三", credit_code "91...", address "北京..."
- **THEN** the migration creates an Entity with entity_type="org", name="XX科技有限公司", attributes={"legal_person": "张三", "credit_code": "91...", "address": "北京..."}

### Requirement: Person to Entity migration
The system SHALL migrate all Person records to Entity records with entity_type "person" and parent_id linking to the corresponding org entity.

#### Scenario: Person migrated to person entity
- **WHEN** a Person record exists with name "李四", company_id=5, education "本科", position "项目经理"
- **THEN** the migration creates an Entity with entity_type="person", name="李四", parent_id=mapped_entity_id_for_company_5, attributes={"education": "本科", "position": "项目经理", "id_number": "..."}

### Requirement: Material to Document+Revision+File migration
The system SHALL migrate each Material record into a Document (with folder assignment based on material_type), a Revision (version 1), and a File record (pointing to the existing image file).

#### Scenario: Material with known type migrated
- **WHEN** a Material record exists with material_type "license", title "营业执照", image_path "data/images/xxx.png", and extracted_json containing structured data
- **THEN** the migration creates:
  - A Document in the "business-license" folder, with doc_type matching "business-license", title "营业执照", metadata populated from extracted_json, and status "active"
  - A Revision with version_number=1, is_current=true
  - A File with file_type "original", storage_path pointing to the existing image file

#### Scenario: Material with unknown type migrated
- **WHEN** a Material record exists with material_type null or unrecognized
- **THEN** the migration creates a Document in a "unsorted" folder with a generic doc type, and logs a warning

### Requirement: Entity-document linking during migration
The system SHALL create DocumentEntity records based on the legacy Material's company_id and person_id.

#### Scenario: Material linked to company
- **WHEN** a Material has company_id=5
- **THEN** the migration creates a DocumentEntity linking the new Document to the mapped org entity with role "owner"

#### Scenario: Material linked to person
- **WHEN** a Material has person_id=10
- **THEN** the migration creates a DocumentEntity linking the new Document to the mapped person entity with role "subject"

### Requirement: MaterialVersion to Revision migration
The system SHALL migrate MaterialVersion records into additional Revision records on the corresponding Document.

#### Scenario: Material with version history
- **WHEN** MaterialVersion records exist for a Material with version_numbers 1, 2, 3
- **THEN** the migration creates corresponding Revision records with matching version_numbers, with only the highest version marked is_current=true

### Requirement: Migration report and rollback
The system SHALL output a migration report and support rollback.

#### Scenario: Migration report
- **WHEN** migration completes
- **THEN** the script prints a summary: total companies migrated, total persons migrated, total materials migrated, total skipped/failed records with reasons

#### Scenario: Database backup before migration
- **WHEN** the migration script starts
- **THEN** it first copies the database file to `{db_path}.pre-dms-migration.backup`

#### Scenario: Rollback
- **WHEN** the user wants to undo the migration
- **THEN** they can restore the backup file to revert to the pre-migration state

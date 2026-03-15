## ADDED Requirements

### Requirement: Folder data model
The system SHALL store folders with the following fields: id (auto-increment), name (string, required), parent_id (nullable self-reference), path (materialized path string, unique), description (nullable string), sort_order (integer, default 0), created_by (nullable user reference), created_at (datetime), updated_at (datetime).

#### Scenario: Root folder creation
- **WHEN** a folder is created with no parent_id
- **THEN** the folder is saved with path equal to `/<slug>/` where slug is derived from the name

#### Scenario: Nested folder creation
- **WHEN** a folder is created with parent_id pointing to an existing folder with path `/company-qualifications/`
- **THEN** the folder is saved with path equal to `/<parent-path><slug>/` (e.g., `/company-qualifications/business-license/`)

### Requirement: Folder tree retrieval
The system SHALL provide an API endpoint to retrieve the full folder tree as a nested structure.

#### Scenario: Get full folder tree
- **WHEN** a GET request is made to `/api/v2/folders/tree`
- **THEN** the system returns all folders as a nested JSON tree with children arrays, ordered by sort_order

#### Scenario: Get subtree
- **WHEN** a GET request is made to `/api/v2/folders/{id}/tree`
- **THEN** the system returns the specified folder and all its descendants as a nested tree

### Requirement: Folder CRUD operations
The system SHALL provide API endpoints to create, read, update, and delete folders.

#### Scenario: Create folder
- **WHEN** a POST request is made to `/api/v2/folders/` with name and optional parent_id
- **THEN** the system creates the folder, computes its materialized path, and returns the created folder

#### Scenario: Update folder
- **WHEN** a PATCH request is made to `/api/v2/folders/{id}` with updated name or description
- **THEN** the system updates the folder fields and returns the updated folder

#### Scenario: Move folder
- **WHEN** a PATCH request is made to `/api/v2/folders/{id}` with a new parent_id
- **THEN** the system updates the folder's parent_id and recomputes the materialized path for the folder and all its descendants

#### Scenario: Delete empty folder
- **WHEN** a DELETE request is made to `/api/v2/folders/{id}` and the folder contains no documents or child folders
- **THEN** the system deletes the folder and returns success

#### Scenario: Delete non-empty folder rejected
- **WHEN** a DELETE request is made to `/api/v2/folders/{id}` and the folder contains documents or child folders
- **THEN** the system returns a 409 Conflict error with a message indicating the folder is not empty

### Requirement: Seed default folder structure
The system SHALL create a default folder hierarchy on first startup when the folders table is empty.

#### Scenario: First startup seeds folders
- **WHEN** the application starts and the folders table contains zero rows
- **THEN** the system creates the default folder tree: root-level folders for company qualifications (with subfolders: business license, qualification certificates, ISO certifications, honors/awards), personnel qualifications (with subfolders: ID documents, education certificates, professional certificates, vocational qualifications), project records (with subfolders: contracts, acceptance reports), and bid documents (with subfolders: in-progress, archived)

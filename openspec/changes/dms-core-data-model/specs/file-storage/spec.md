## ADDED Requirements

### Requirement: File data model
The system SHALL store file records with the following fields: id (auto-increment), revision_id (required reference to Revision), file_type (string enum: original/thumbnail/extracted_page/ocr_result), filename (string, required), storage_path (string, required — relative path from DATA_DIR), mime_type (nullable string), file_size (integer, default 0), file_hash (nullable string — MD5 hash for deduplication), page_number (nullable integer — for extracted_page type), created_at (datetime).

#### Scenario: Original file record
- **WHEN** a file record is created with file_type "original"
- **THEN** the record stores the path to the originally uploaded file (PDF, image, etc.)

#### Scenario: Extracted page file record
- **WHEN** a file record is created with file_type "extracted_page" and page_number 3
- **THEN** the record stores the path to the extracted page image with the page number for ordering

### Requirement: File serving endpoint
The system SHALL provide an endpoint to serve physical files by file record ID.

#### Scenario: Serve file by ID
- **WHEN** a GET request is made to `/api/v2/files/{file_id}`
- **THEN** the system returns the physical file with correct content-type header

#### Scenario: File not found on disk
- **WHEN** a GET request is made to `/api/v2/files/{file_id}` but the physical file is missing from storage
- **THEN** the system returns a 404 error

#### Scenario: Path traversal prevention
- **WHEN** a file's storage_path contains path traversal characters (../)
- **THEN** the system rejects the request with a 403 error

### Requirement: File upload to revision
The system SHALL allow uploading files to a specific revision.

#### Scenario: Upload file to revision
- **WHEN** a POST request is made to `/api/v2/documents/{doc_id}/revisions/{rev_id}/files/` with a file upload and file_type
- **THEN** the system stores the physical file, computes its hash and size, creates a File record, and returns the file metadata

#### Scenario: Duplicate file detection
- **WHEN** a file is uploaded whose MD5 hash matches an existing file in the same revision
- **THEN** the system returns a 409 Conflict indicating a duplicate file

### Requirement: Legacy file path compatibility
The system SHALL continue serving files via the legacy `/api/files/{filename}` endpoint.

#### Scenario: Legacy file endpoint
- **WHEN** a GET request is made to `/api/files/{filename}`
- **THEN** the system searches for the file in both `data/files/` and `data/images/` directories and serves it if found

## ADDED Requirements

### Requirement: Single upload endpoint accepts PDF, image, and Word files
The system SHALL provide a `POST /api/v2/upload/` endpoint that accepts a single file upload via multipart form data. The endpoint SHALL accept files with MIME types: `application/pdf`, `image/jpeg`, `image/png`, `image/tiff`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, and `application/msword`. The endpoint SHALL reject files with unsupported MIME types with HTTP 400.

#### Scenario: Upload a PDF file
- **WHEN** a user sends `POST /api/v2/upload/` with a PDF file
- **THEN** the system returns HTTP 201 with `{ document_id, revision_id, status: "processing" }`

#### Scenario: Upload a JPEG image
- **WHEN** a user sends `POST /api/v2/upload/` with a JPEG image
- **THEN** the system returns HTTP 201 with `{ document_id, revision_id, status: "processing" }`

#### Scenario: Upload an unsupported file type
- **WHEN** a user sends `POST /api/v2/upload/` with a `.zip` file
- **THEN** the system returns HTTP 400 with an error message indicating unsupported file type

### Requirement: Upload creates Document, Revision, and File synchronously
The system SHALL synchronously create a DmsDocument (status=draft), a Revision (version=1), and a DmsFile (file_type=original) when a file is uploaded. The file SHALL be stored at `data/dms_files/{doc_id}/{rev_id}/{hash}_{filename}`. The document title SHALL default to the filename (without extension) if no title is provided.

#### Scenario: Records created on upload
- **WHEN** a user uploads a file named "营业执照.pdf"
- **THEN** a DmsDocument with title "营业执照" and status "draft" is created
- **AND** a Revision with version 1 is created linked to the document
- **AND** a DmsFile with file_type "original" is created linked to the revision
- **AND** the physical file is stored under `data/dms_files/`

#### Scenario: Upload with explicit title
- **WHEN** a user uploads a file with form field `title` set to "公司营业执照2024"
- **THEN** the DmsDocument title is "公司营业执照2024" instead of the filename

### Requirement: Upload triggers async background processing
The system SHALL return the upload response immediately after creating records, then trigger background processing asynchronously using a Python thread. The background processing SHALL NOT block the HTTP response.

#### Scenario: Immediate response with async processing
- **WHEN** a user uploads a PDF file
- **THEN** the HTTP response returns within 2 seconds
- **AND** background processing begins in a separate thread
- **AND** the document's `_processing` key in meta_json is set to `{ status: "pending" }`

### Requirement: Upload accepts optional metadata fields
The system SHALL accept optional form fields: `title` (string), `folder_id` (integer), `doc_type_id` (integer), `notes` (string). If `folder_id` or `doc_type_id` are provided, they SHALL be set on the document directly (skipping auto-classification for those fields).

#### Scenario: Upload with explicit folder assignment
- **WHEN** a user uploads a file with `folder_id=5`
- **THEN** the document is assigned to folder ID 5
- **AND** auto-classification does NOT override the folder assignment

#### Scenario: Upload with no optional fields
- **WHEN** a user uploads a file with only the file field
- **THEN** the document is created with no folder, no doc_type, and auto-classification will assign them

### Requirement: Upload endpoint requires authentication
The system SHALL require a valid authentication token for the upload endpoint. Unauthenticated requests SHALL receive HTTP 401.

#### Scenario: Unauthenticated upload attempt
- **WHEN** a user sends `POST /api/v2/upload/` without an auth token
- **THEN** the system returns HTTP 401

### Requirement: Processing status queryable via document detail
The system SHALL expose the processing status through `GET /api/v2/documents/{id}`. The `_processing` key in meta_json SHALL contain `status` (pending/ocr_running/classifying/linking_entities/completed/failed) and optionally `error` (on failure) and `completed_at` (on success).

#### Scenario: Query processing status mid-OCR
- **WHEN** a user queries `GET /api/v2/documents/{id}` while OCR is running
- **THEN** the response includes meta_json with `_processing.status = "ocr_running"`

#### Scenario: Query processing status after completion
- **WHEN** a user queries `GET /api/v2/documents/{id}` after processing completes
- **THEN** the response includes meta_json with `_processing.status = "completed"` and `_processing.completed_at`

#### Scenario: Query processing status after failure
- **WHEN** a user queries `GET /api/v2/documents/{id}` after processing fails
- **THEN** the response includes meta_json with `_processing.status = "failed"` and `_processing.error`

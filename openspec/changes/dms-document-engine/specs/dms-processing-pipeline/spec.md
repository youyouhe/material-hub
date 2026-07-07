## ADDED Requirements

### Requirement: OCR processing for uploaded files
The system SHALL send uploaded PDF and image files to the OCR service using the existing `ocr_client.py` module. OCR results SHALL be cached using `ocr_cache.py` (keyed by file content hash). The system SHALL update `_processing.status` to "ocr_running" before starting OCR.

#### Scenario: OCR on a PDF file
- **WHEN** a PDF file is uploaded and background processing starts
- **THEN** the system extracts relevant pages and sends them to OCR
- **AND** OCR results are cached by file hash
- **AND** `_processing.status` transitions from "pending" to "ocr_running"

#### Scenario: OCR cache hit
- **WHEN** a file with the same content hash was previously OCR'd
- **THEN** the system uses the cached OCR result instead of calling the OCR service again

#### Scenario: OCR service unavailable
- **WHEN** the OCR service is down or returns an error
- **THEN** `_processing.status` is set to "failed"
- **AND** `_processing.error` contains the error description
- **AND** the document remains in "draft" status

### Requirement: LLM analysis for document classification
The system SHALL pass OCR text to the LLM analysis module (`ocr_agent.py`'s `intelligent_extract`) to determine material_type, extract structured data (company name, person name, dates, certificate numbers), and detect expiry dates. The system SHALL update `_processing.status` to "classifying" during this step.

#### Scenario: LLM identifies a business license
- **WHEN** OCR text from a business license is analyzed by LLM
- **THEN** LLM returns `material_type = "license"` with extracted company name, registration number, and dates
- **AND** extracted data is stored in the document's meta_json

#### Scenario: LLM identifies a contract
- **WHEN** OCR text from a contract is analyzed by LLM
- **THEN** LLM returns `material_type = "contract"` with extracted parties, contract value, and dates

#### Scenario: LLM cannot determine type
- **WHEN** LLM analysis returns an unknown or empty material_type
- **THEN** the document's doc_type remains unset
- **AND** the document's folder remains unset
- **AND** processing continues (does not fail)

### Requirement: DocType auto-mapping from LLM material_type
The system SHALL map the LLM-returned `material_type` to a DMS DocType code using a static mapping dictionary. The mapping SHALL include: license→business-license, iso_cert→iso-cert, certificate→professional-cert, id_card→id-card, education→education-cert, contract→contract, acceptance→acceptance-report, honor→honor-award, qualification→qualification-cert. If the document already has a doc_type_id (set during upload), auto-mapping SHALL be skipped.

#### Scenario: Auto-assign DocType from LLM result
- **WHEN** LLM returns `material_type = "license"` and no doc_type_id was provided at upload
- **THEN** the system sets the document's doc_type to the DocType with code "business-license"

#### Scenario: Skip auto-assign when DocType pre-set
- **WHEN** LLM returns `material_type = "license"` but doc_type_id was provided at upload
- **THEN** the system does NOT override the existing doc_type

#### Scenario: Unknown material_type has no mapping
- **WHEN** LLM returns a material_type not in the mapping dictionary
- **THEN** the document's doc_type remains unset

### Requirement: Auto-filing into Folder based on DocType
The system SHALL map the assigned DocType code to a default Folder path using a static mapping dictionary (e.g., business-license→/公司资质/营业执照/). If the document already has a folder_id (set during upload), auto-filing SHALL be skipped. If the target folder does not exist, auto-filing SHALL be skipped without error.

#### Scenario: Auto-file a business license
- **WHEN** a document is classified as DocType "business-license" and no folder_id was pre-set
- **THEN** the system assigns the document to the folder at path "/公司资质/营业执照/"

#### Scenario: Skip auto-file when folder pre-set
- **WHEN** a document has folder_id set from upload
- **THEN** the system does NOT override the existing folder assignment

### Requirement: Entity auto-linking from extracted data
The system SHALL use `create_entity_from_extraction()` from `ocr_agent.py` to determine entity type and data from the LLM extraction. The system SHALL create or match a DMS Entity record and link it to the document via DocumentEntity with role "owner". The system SHALL update `_processing.status` to "linking_entities" during this step.

#### Scenario: Link extracted company to document
- **WHEN** LLM extraction contains a company name "XX建设有限公司"
- **THEN** the system finds or creates an Entity(entity_type="org", name="XX建设有限公司")
- **AND** creates a DocumentEntity link with role "owner"

#### Scenario: Link extracted person to document
- **WHEN** LLM extraction contains a person name "张三" (e.g., from ID card or certificate)
- **THEN** the system finds or creates an Entity(entity_type="person", name="张三")
- **AND** creates a DocumentEntity link with role "owner"

#### Scenario: No entity extracted
- **WHEN** LLM extraction does not contain identifiable entity information
- **THEN** no DocumentEntity link is created
- **AND** processing continues without error

### Requirement: PDF page extraction as File records
The system SHALL extract selected pages from PDF files as individual DmsFile records with file_type "extracted_page". Page selection SHALL use the existing `page_extraction_strategy.py` for smart page selection. For contract-type documents, `contract_page_analyzer.py` SHALL be used for key page detection. Extracted pages SHALL be stored as PNG images.

#### Scenario: Extract pages from a multi-page PDF
- **WHEN** a 10-page PDF is uploaded
- **THEN** the page extraction strategy selects relevant pages
- **AND** each selected page is rendered as a PNG image
- **AND** each PNG is stored as a DmsFile with file_type "extracted_page" linked to the same revision

#### Scenario: Extract key pages from a contract PDF
- **WHEN** a contract PDF is uploaded and classified as DocType "contract"
- **THEN** the contract page analyzer identifies key pages (cover, signature, scope)
- **AND** those pages are extracted as DmsFile records

#### Scenario: Single-page PDF
- **WHEN** a single-page PDF is uploaded
- **THEN** only that page is extracted as an "extracted_page" DmsFile

### Requirement: Thumbnail generation
The system SHALL generate a thumbnail for each uploaded file. For images, the thumbnail SHALL be created using Pillow resized to 200px width maintaining aspect ratio. For PDFs, the thumbnail SHALL be the first page rendered at 200px width using PyMuPDF. Thumbnails SHALL be stored as DmsFile with file_type "thumbnail" linked to the same revision.

#### Scenario: Thumbnail for an image upload
- **WHEN** a JPEG image (3000x2000px) is uploaded
- **THEN** a thumbnail (200x133px) is generated and stored as DmsFile(file_type="thumbnail")

#### Scenario: Thumbnail for a PDF upload
- **WHEN** a PDF file is uploaded
- **THEN** the first page is rendered as a 200px-wide PNG thumbnail
- **AND** stored as DmsFile(file_type="thumbnail")

### Requirement: Expiry date extraction and storage
The system SHALL extract expiry dates from documents using `extract_expiry_date()` from `ocr_agent.py`. If an expiry date is found, it SHALL be stored on DmsDocument.expiry_date.

#### Scenario: Document with expiry date
- **WHEN** a certificate with expiry date "2025-12-31" is processed
- **THEN** the document's expiry_date is set to 2025-12-31

#### Scenario: Document without expiry date
- **WHEN** a document without any date information is processed
- **THEN** the document's expiry_date remains NULL

### Requirement: Processing pipeline completes with status update
The system SHALL set `_processing.status` to "completed" and `_processing.completed_at` to the current ISO timestamp when all processing steps finish successfully. The full pipeline order SHALL be: pending → ocr_running → classifying → linking_entities → completed.

#### Scenario: Successful full pipeline
- **WHEN** all processing steps complete without error
- **THEN** `_processing.status` is "completed"
- **AND** `_processing.completed_at` contains the completion timestamp
- **AND** extracted metadata is stored in document meta_json

### Requirement: Word files stored without content extraction
The system SHALL store Word (.docx/.doc) files as-is without content extraction or OCR. Word files SHALL still have a thumbnail generated (using a generic document icon or first-page render if possible). Processing for Word files SHALL skip OCR and LLM steps and go directly to "completed".

#### Scenario: Upload a Word document
- **WHEN** a .docx file is uploaded
- **THEN** the file is stored as DmsFile(file_type="original")
- **AND** `_processing.status` goes directly to "completed"
- **AND** no OCR or LLM analysis is performed

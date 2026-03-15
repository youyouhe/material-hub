## ADDED Requirements

### Requirement: Unified search endpoint with keyword and facets
The system SHALL provide `GET /api/v2/search` accepting query parameters: `q` (keyword string), `folder_id` (integer), `doc_type_id` (integer), `entity_id` (integer), `tag_id` (integer), `status` (string), `expiry_before` (date), `expiry_after` (date), `sort` (string: relevance/date/title, default relevance), `limit` (integer, default 50), `offset` (integer, default 0).

#### Scenario: Keyword search
- **WHEN** `GET /api/v2/search?q=营业执照`
- **THEN** documents matching "营业执照" in title, OCR text, or entity names are returned ranked by relevance

#### Scenario: Faceted search without keyword
- **WHEN** `GET /api/v2/search?folder_id=5&doc_type_id=3`
- **THEN** documents in folder 5 with DocType 3 are returned ordered by updated_at desc

#### Scenario: Combined keyword and facet search
- **WHEN** `GET /api/v2/search?q=ISO&entity_id=1`
- **THEN** only documents matching "ISO" that are also linked to entity 1 are returned

#### Scenario: Search with expiry date range
- **WHEN** `GET /api/v2/search?expiry_before=2025-12-31&expiry_after=2025-01-01`
- **THEN** only documents with expiry_date between 2025-01-01 and 2025-12-31 are returned

### Requirement: Search results include document detail and highlight context
The search response SHALL include for each result: document ID, title, status, DocType, folder, entity names, expiry_date, thumbnail URL, created_at, and a `snippet` field containing a text excerpt around the matched keywords (when a keyword search is performed).

#### Scenario: Search result with snippet
- **WHEN** searching for "信用代码" and a document's OCR text contains "统一社会信用代码：91110000..."
- **THEN** the result includes a `snippet` field with "...统一社会**信用代码**：91110000..."

#### Scenario: Search result without keyword (no snippet)
- **WHEN** searching with facets only (no `q` parameter)
- **THEN** the `snippet` field is null

### Requirement: Search response includes total count and pagination
The search response SHALL include `total` (total matching documents), `limit`, `offset`, and `results` array. Pagination SHALL work with both keyword and facet-only queries.

#### Scenario: Paginated search results
- **WHEN** 100 documents match and `offset=20&limit=10`
- **THEN** results contain documents 21-30 with `total=100`

### Requirement: Search endpoint requires authentication
The system SHALL require a valid authentication token for the search endpoint. Unauthenticated requests SHALL receive HTTP 401.

#### Scenario: Unauthenticated search
- **WHEN** `GET /api/v2/search?q=test` without auth token
- **THEN** HTTP 401 is returned

### Requirement: Version matching for certificate-type documents
The system SHALL, during the upload processing pipeline, check if a newly uploaded document matches an existing document by entity + DocType for versionable types (business-license, iso-cert, qualification-cert, professional-cert, education-cert, id-card). If a match is found and the new document has a later expiry/issue date, the system SHALL create the new upload as a new Revision on the existing Document instead of a standalone document.

#### Scenario: New ISO cert matches existing one
- **WHEN** a new ISO 9001 certificate is uploaded for entity "XX建设公司"
- **AND** an existing document with DocType "iso-cert" linked to "XX建设公司" exists
- **AND** the new certificate has a later expiry date
- **THEN** the new file is added as a new Revision on the existing document
- **AND** the old revision is marked as non-current

#### Scenario: No matching document exists
- **WHEN** a new certificate is uploaded for an entity with no prior documents of that DocType
- **THEN** a new standalone Document is created (normal flow)

#### Scenario: New document is older than existing
- **WHEN** a certificate is uploaded with an earlier expiry date than the existing one
- **THEN** it is kept as a standalone draft document (no auto-version merge)
- **AND** a note is added to meta_json indicating a potential duplicate was detected

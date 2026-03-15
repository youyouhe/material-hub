## ADDED Requirements

### Requirement: BidRequirement data model
The system SHALL store bid requirements with fields: id, bid_project_id (FK to dms_bid_projects), doc_type_id (FK to dms_doc_types, optional), title (string, e.g. "营业执照"), description (optional), is_required (boolean, default true), sort_order (int), created_at, updated_at. The table SHALL be named `dms_bid_requirements`.

#### Scenario: Create requirement with doc_type reference
- **WHEN** a BidRequirement is created with title="营业执照" and doc_type_id pointing to the business-license doc type
- **THEN** a row is inserted into dms_bid_requirements with the given doc_type_id

#### Scenario: Create requirement without doc_type
- **WHEN** a BidRequirement is created with title="公司简介" and no doc_type_id
- **THEN** a row is inserted with doc_type_id=null (custom requirement, no auto-match available)

### Requirement: BidDocument junction model
The system SHALL store bid-document links with fields: id, bid_requirement_id (FK), document_id (FK to dms_documents), status (pending/linked/verified), linked_by (user id), linked_at, notes (optional). Table: `dms_bid_documents`. A unique constraint SHALL exist on (bid_requirement_id, document_id).

#### Scenario: Link document to requirement
- **WHEN** a DmsDocument is linked to a BidRequirement
- **THEN** a BidDocument record is created with status="linked"

#### Scenario: Prevent duplicate link
- **WHEN** the same document_id is linked to the same bid_requirement_id twice
- **THEN** the system returns 409

### Requirement: BidRequirement CRUD API
The system SHALL provide endpoints: POST /api/v2/bids/{bid_id}/requirements (create), GET /api/v2/bids/{bid_id}/requirements (list), PATCH /api/v2/bids/{bid_id}/requirements/{req_id} (update), DELETE /api/v2/bids/{bid_id}/requirements/{req_id} (delete). Write operations SHALL require editor role.

#### Scenario: Create requirement
- **WHEN** POST /api/v2/bids/{bid_id}/requirements with title and optional doc_type_id
- **THEN** a new requirement is created for the bid project

#### Scenario: List requirements with fulfillment status
- **WHEN** GET /api/v2/bids/{bid_id}/requirements
- **THEN** each requirement includes its linked documents and fulfillment status (fulfilled if at least one linked/verified document exists)

#### Scenario: Bulk create requirements from doc_type category
- **WHEN** POST /api/v2/bids/{bid_id}/requirements/from-category with category="company"
- **THEN** requirements are created for all doc types in the "company" category that don't already exist as requirements

### Requirement: Link document to requirement
The system SHALL provide POST /api/v2/bids/{bid_id}/requirements/{req_id}/documents to link a DmsDocument to a requirement, and DELETE to unlink.

#### Scenario: Link existing document
- **WHEN** POST with document_id pointing to an active DmsDocument
- **THEN** a BidDocument record is created with status="linked"

#### Scenario: Link non-existent document
- **WHEN** POST with document_id that doesn't exist
- **THEN** the system returns 404

#### Scenario: Unlink document
- **WHEN** DELETE /api/v2/bids/{bid_id}/requirements/{req_id}/documents/{doc_id}
- **THEN** the BidDocument record is deleted

### Requirement: Auto-match documents for requirements
The system SHALL provide GET /api/v2/bids/{bid_id}/requirements/{req_id}/suggestions that returns candidate DmsDocuments matching the requirement's doc_type_id. Results SHALL be filtered to active/draft documents and ordered by relevance.

#### Scenario: Auto-match with doc_type
- **WHEN** a requirement has doc_type_id pointing to "business-license" and the DMS has 3 active business license documents
- **THEN** the suggestions endpoint returns those 3 documents

#### Scenario: Auto-match with no doc_type
- **WHEN** a requirement has no doc_type_id
- **THEN** the suggestions endpoint returns an empty list

#### Scenario: Auto-match filters out archived documents
- **WHEN** the DMS has 2 active and 1 archived business license documents
- **THEN** only the 2 active documents are returned as suggestions

### Requirement: Bid readiness/checklist API
The system SHALL provide GET /api/v2/bids/{bid_id}/checklist that returns a summary of all requirements with their fulfillment status, plus aggregate statistics.

#### Scenario: Full checklist response
- **WHEN** GET /api/v2/bids/{bid_id}/checklist for a bid with 5 requirements (3 fulfilled, 2 missing)
- **THEN** the response includes: total=5, fulfilled=3, missing=2, percentage=60, and a list of each requirement with its status and linked documents

#### Scenario: Checklist detects deleted documents
- **WHEN** a requirement was linked to a document that has since been deleted
- **THEN** the checklist marks that requirement as "missing" (the BidDocument link exists but the document is gone)

### Requirement: Verify linked document
The system SHALL provide PATCH /api/v2/bids/{bid_id}/requirements/{req_id}/documents/{doc_id} to update the BidDocument status to "verified", indicating the document has been reviewed and confirmed suitable.

#### Scenario: Verify a linked document
- **WHEN** PATCH with status="verified" on a linked BidDocument
- **THEN** the status is updated to "verified"

#### Scenario: Cannot verify unlinked document
- **WHEN** PATCH on a BidDocument that doesn't exist
- **THEN** the system returns 404

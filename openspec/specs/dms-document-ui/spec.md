## ADDED Requirements

### Requirement: Document list page
The documents page SHALL display a paginated table of documents from `GET /api/v2/documents`. Each row SHALL show title, doc type, status, entity links, expiry date, and updated timestamp. The list SHALL support filtering by folder_id, doc_type_id, status, and entity_id query parameters.

#### Scenario: Document list loads with pagination
- **WHEN** user navigates to the documents page
- **THEN** the page fetches documents from `/api/v2/documents` with default limit/offset and displays them in a table with pagination controls

#### Scenario: Folder filter applied from sidebar
- **WHEN** user selects a folder in the sidebar tree
- **THEN** the document list re-fetches with `folder_id` parameter and shows only documents in that folder

#### Scenario: Status filter
- **WHEN** user selects a status from the filter dropdown (active, draft, archived, superseded)
- **THEN** the document list re-fetches with `status` parameter applied

### Requirement: Document detail panel
Clicking a document in the list SHALL open an inline detail panel (slide-over or right panel) showing: title, status badge, doc type, folder path, entity links, tags, lock status, expiry date, and revision history. The panel SHALL NOT navigate away from the document list.

#### Scenario: Detail panel opens on row click
- **WHEN** user clicks a document row in the list
- **THEN** a detail panel slides open showing the document's full metadata fetched from `GET /api/v2/documents/{id}`

#### Scenario: Revision history displayed
- **WHEN** the detail panel opens
- **THEN** it shows revision history with version numbers, creation dates, and file download links

#### Scenario: Entity links displayed
- **WHEN** a document has linked entities
- **THEN** the detail panel shows entity names with their roles (owner, subject, etc.)

#### Scenario: Tag display
- **WHEN** a document has tags
- **THEN** the detail panel shows tags as badge chips

### Requirement: Upload page with v2 flow
The upload page SHALL use `POST /api/v2/upload` to upload files. After upload, the page SHALL show the upload queue from `GET /api/v2/upload/queue` with approve/reject actions. Users with editor role SHALL be able to approve uploads (setting doc type, folder, title) or reject them.

#### Scenario: File upload
- **WHEN** user selects a file and clicks upload
- **THEN** the file is sent to `POST /api/v2/upload` and appears in the upload queue with status "pending"

#### Scenario: Approve upload
- **WHEN** editor clicks approve on a queued upload and fills in metadata (title, doc_type, folder)
- **THEN** the system calls `POST /api/v2/upload/{id}/approve` and the item moves to "approved" status

#### Scenario: Reject upload
- **WHEN** editor clicks reject on a queued upload
- **THEN** the system calls `POST /api/v2/upload/{id}/reject` and the item moves to "rejected" status

### Requirement: Search page with full-text search
The search page SHALL provide a search input that queries `GET /api/v2/search?q=...`. Results SHALL display document title, snippet with highlighted matches, doc type, and status. Results SHALL be clickable to open the document detail panel.

#### Scenario: Search returns results
- **WHEN** user types a query and submits
- **THEN** the page fetches from `/api/v2/search?q={query}` and displays matching documents with highlighted snippets

#### Scenario: Empty search
- **WHEN** user submits an empty query
- **THEN** the page shows a prompt to enter search terms instead of making an API call

### Requirement: Expiry dashboard
The expiry page SHALL display documents expiring soon from `GET /api/v2/expiry`. It SHALL show documents grouped by time horizon (expired, expiring within 30 days, expiring within 90 days). Each entry SHALL show document title, expiry date, doc type, and linked entity.

#### Scenario: Expiry dashboard loads
- **WHEN** user navigates to the expiry page
- **THEN** the page fetches from `/api/v2/expiry` and groups results by expiry urgency

#### Scenario: Click expiring document
- **WHEN** user clicks a document in the expiry list
- **THEN** the document detail panel opens for that document

### Requirement: Document editing for editors
Users with editor or admin role SHALL be able to edit document metadata (title, doc_type, folder, tags, entity links) via the detail panel. Viewers SHALL see read-only detail. Edit actions SHALL call `PATCH /api/v2/documents/{id}`.

#### Scenario: Editor sees edit controls
- **WHEN** a user with role "editor" opens the document detail panel
- **THEN** edit buttons and inline-edit fields are visible for title, doc type, folder, tags, and entities

#### Scenario: Viewer sees read-only
- **WHEN** a user with role "viewer" opens the document detail panel
- **THEN** no edit controls are visible; all fields are display-only

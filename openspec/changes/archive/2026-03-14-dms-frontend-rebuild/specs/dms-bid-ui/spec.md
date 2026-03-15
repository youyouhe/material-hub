## ADDED Requirements

### Requirement: Bid project list page
The bids page SHALL display a list of bid projects from `GET /api/v2/bids`. Each card/row SHALL show project name, bid number, buyer, status badge, deadline, and a requirement fulfillment progress bar (from `requirements_summary`). The list SHALL support filtering by status and text search.

#### Scenario: Bid list loads
- **WHEN** user navigates to the bids page
- **THEN** the page fetches from `/api/v2/bids` and displays bid projects with their requirement summary progress

#### Scenario: Filter by status
- **WHEN** user selects a status filter (planning, active, submitted, won, lost, cancelled)
- **THEN** the list re-fetches with `status` parameter and shows only matching projects

#### Scenario: Search bids
- **WHEN** user types in the search field
- **THEN** the list re-fetches with `q` parameter filtering by project name

### Requirement: Bid project detail page
Clicking a bid project SHALL navigate to a detail page showing: project info (name, bid number, buyer, budget, deadline, description, status), team members, and the requirements checklist. The page SHALL fetch data from `GET /api/v2/bids/{id}` and `GET /api/v2/bids/{id}/checklist`.

#### Scenario: Detail page loads
- **WHEN** user clicks a bid project from the list
- **THEN** the page state changes to 'bid-detail' with the selected bid ID, and the detail page renders project info and checklist

#### Scenario: Status badge with transition
- **WHEN** an editor views a bid detail page
- **THEN** the status badge shows current status and a dropdown/button allows transitioning to valid next states via `PATCH /api/v2/bids/{id}/status`

### Requirement: Requirements checklist UI
The bid detail page SHALL display requirements as a checklist from `GET /api/v2/bids/{id}/checklist`. Each requirement item SHALL show: title, required/optional badge, fulfillment status (fulfilled/missing), and linked documents. A progress summary SHALL show "N/M requirements fulfilled (X%)".

#### Scenario: Checklist renders with progress
- **WHEN** the bid detail page loads
- **THEN** the checklist displays all requirements with visual fulfillment indicators and a progress bar showing the percentage complete

#### Scenario: Fulfilled requirement display
- **WHEN** a requirement has linked documents
- **THEN** it shows a green checkmark, the linked document titles, and their verification status

#### Scenario: Missing requirement display
- **WHEN** a requirement has no linked documents
- **THEN** it shows a red/amber indicator and an "Add Document" action button

### Requirement: Document linking for requirements
Editors SHALL be able to link documents to requirements. Clicking "Add Document" on a requirement SHALL show suggestions from `GET /api/v2/bids/{bid_id}/requirements/{req_id}/suggestions` (auto-matched by doc_type). Users SHALL also be able to search and manually link any document via `POST /api/v2/bids/{bid_id}/requirements/{req_id}/documents`.

#### Scenario: Auto-match suggestions shown
- **WHEN** editor clicks "Add Document" on a requirement with a doc_type
- **THEN** the UI fetches suggestions from the suggestions endpoint and displays matching documents

#### Scenario: Manual document link
- **WHEN** editor searches for a document and selects one to link
- **THEN** the system calls the link document endpoint and the requirement updates to show fulfillment

#### Scenario: Unlink document
- **WHEN** editor clicks unlink on a linked document
- **THEN** the system calls the unlink endpoint and the requirement reverts to missing status

### Requirement: Bid project creation and editing
Editors SHALL be able to create new bid projects via a form that calls `POST /api/v2/bids/`. The form SHALL include fields: name (required), bid number, buyer, budget, deadline (date picker), and description. Editing SHALL use `PATCH /api/v2/bids/{id}`.

#### Scenario: Create bid project
- **WHEN** editor fills in the create form and submits
- **THEN** the system calls `POST /api/v2/bids/` and navigates to the new project's detail page

#### Scenario: Edit bid project
- **WHEN** editor modifies fields on the bid detail page and saves
- **THEN** the system calls `PATCH /api/v2/bids/{id}` and the page reflects updated values

### Requirement: Team member management
The bid detail page SHALL show team members from the project data. Editors SHALL be able to add team members (selecting an entity and role) via `POST /api/v2/bids/{id}/team` and remove them via `DELETE /api/v2/bids/{id}/team/{member_id}`.

#### Scenario: Add team member
- **WHEN** editor selects an entity and role and clicks add
- **THEN** the system calls the team endpoint and the new member appears in the team list

#### Scenario: Remove team member
- **WHEN** editor clicks remove on a team member
- **THEN** the system calls the delete team endpoint and the member is removed from the list

### Requirement: Bulk requirement creation from category
Editors SHALL be able to bulk-create requirements from a doc type category via `POST /api/v2/bids/{bid_id}/requirements/from-category`. The UI SHALL present available categories and show how many requirements will be created.

#### Scenario: Bulk create from category
- **WHEN** editor selects a category and confirms
- **THEN** the system calls the from-category endpoint and the checklist updates with new requirement items

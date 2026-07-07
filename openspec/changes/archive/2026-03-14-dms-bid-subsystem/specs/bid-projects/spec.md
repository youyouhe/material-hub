## ADDED Requirements

### Requirement: BidProject data model
The system SHALL store bid projects with fields: id, name, bid_number (optional), buyer (procuring entity name), folder_id (FK to dms_folders), status, budget (optional string), deadline (optional date), description, result (won/lost/cancelled reason), created_by, created_at, updated_at. The table SHALL be named `dms_bid_projects`.

#### Scenario: Create bid project record
- **WHEN** a BidProject is created with name="XX信息化采购" and buyer="XX市政府"
- **THEN** a row is inserted into dms_bid_projects with status="planning" and auto-generated timestamps

### Requirement: BidProject lifecycle management
The system SHALL enforce status transitions: planning → active, active → submitted, submitted → won/lost/cancelled. Invalid transitions SHALL be rejected with 409.

#### Scenario: Valid transition from planning to active
- **WHEN** a bid project in "planning" status is updated to "active"
- **THEN** the status is updated and the response includes the new status

#### Scenario: Invalid transition from planning to submitted
- **WHEN** a bid project in "planning" status is updated to "submitted"
- **THEN** the system returns 409 with detail explaining the invalid transition

#### Scenario: Terminal status prevents further transitions
- **WHEN** a bid project in "won" status is updated to any other status
- **THEN** the system returns 409

### Requirement: BidProject CRUD API
The system SHALL provide endpoints: POST /api/v2/bids (create), GET /api/v2/bids (list with filters), GET /api/v2/bids/{id} (detail), PATCH /api/v2/bids/{id} (update), DELETE /api/v2/bids/{id} (delete). Write operations SHALL require editor role.

#### Scenario: Create bid project
- **WHEN** POST /api/v2/bids with name, buyer, and optional fields
- **THEN** a new bid project is created with status "planning" and a dedicated folder is auto-created

#### Scenario: List bid projects with status filter
- **WHEN** GET /api/v2/bids?status=active
- **THEN** only bid projects with status "active" are returned, with pagination

#### Scenario: Get bid project detail
- **WHEN** GET /api/v2/bids/{id}
- **THEN** the response includes project metadata, team members, requirement summary (total/fulfilled/missing counts), and folder info

#### Scenario: Delete bid project
- **WHEN** DELETE /api/v2/bids/{id}
- **THEN** the bid project and its requirements/team members/bid-documents are deleted (cascade), but linked DMS documents are NOT deleted

### Requirement: Auto-create folder for bid project
The system SHALL automatically create a folder under `/投标文件/进行中/` named after the bid project when a new bid project is created. The folder_id SHALL be stored on the bid project record.

#### Scenario: Folder created on bid project creation
- **WHEN** a bid project named "XX采购项目" is created
- **THEN** a folder named "XX采购项目" is created under the "进行中" subfolder of "投标文件", and the bid project's folder_id points to it

#### Scenario: Folder parent not found gracefully handled
- **WHEN** a bid project is created but the "投标文件/进行中" folder doesn't exist
- **THEN** the bid project is still created with folder_id=null and a warning is logged

### Requirement: BidTeamMember management
The system SHALL store team member assignments with fields: id, bid_project_id (FK), entity_id (FK to dms_entities), role (string, e.g. "项目经理"), created_at. Endpoints: POST /api/v2/bids/{id}/team (add member), GET /api/v2/bids/{id}/team (list), DELETE /api/v2/bids/{id}/team/{member_id} (remove).

#### Scenario: Add team member
- **WHEN** POST /api/v2/bids/{id}/team with entity_id and role="项目经理"
- **THEN** a team member record is created linking the entity to the bid project

#### Scenario: Prevent duplicate team member with same role
- **WHEN** POST /api/v2/bids/{id}/team with an entity_id and role that already exists
- **THEN** the system returns 409

#### Scenario: List team members with entity details
- **WHEN** GET /api/v2/bids/{id}/team
- **THEN** the response includes team member records with entity name and type

### Requirement: BidProject status change updates folder
The system SHALL move the bid project's folder from "进行中" to "已归档" when the status transitions to a terminal state (won/lost/cancelled).

#### Scenario: Folder moved on bid won
- **WHEN** a bid project transitions from "submitted" to "won"
- **THEN** the associated folder's parent is changed to "已归档" and its path is recomputed

### Requirement: Audit logging for bid operations
The system SHALL log audit entries for bid project create, update, delete, status changes, and team member changes with target_type="bid_project".

#### Scenario: Bid project creation logged
- **WHEN** a bid project is created
- **THEN** an audit log entry is created with action="create" and target_type="bid_project"

#### Scenario: Status change logged with details
- **WHEN** a bid project status changes from "active" to "submitted"
- **THEN** an audit log entry is created with action="status_change" and details containing old and new status

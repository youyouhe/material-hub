## ADDED Requirements

### Requirement: Sidebar layout replaces top navigation
The application SHALL render a collapsible sidebar on the left side containing all navigation items, replacing the current top tab bar. The main content area SHALL occupy the remaining horizontal space to the right of the sidebar.

#### Scenario: Sidebar renders on authenticated load
- **WHEN** user is authenticated and the app loads
- **THEN** the sidebar is visible on the left with navigation sections and the main content area renders the active page

#### Scenario: Sidebar collapses
- **WHEN** user clicks the collapse toggle on the sidebar
- **THEN** the sidebar collapses to icon-only mode and the main content area expands to fill the freed space

### Requirement: Folder tree in sidebar
The sidebar SHALL display a folder tree loaded from `GET /api/v2/folders`. Clicking a folder SHALL set it as the active folder context, filtering the document list. An "All Documents" option at the top of the tree SHALL clear the folder filter.

#### Scenario: Folder tree loads on mount
- **WHEN** the sidebar mounts
- **THEN** it fetches folders from `/api/v2/folders` and renders them as a nested tree structure

#### Scenario: Clicking a folder filters documents
- **WHEN** user clicks a folder node in the tree
- **THEN** the active page switches to documents view filtered by that folder's ID

#### Scenario: All Documents clears filter
- **WHEN** user clicks "All Documents" at the top of the folder tree
- **THEN** the document list shows all documents without folder filtering

### Requirement: Navigation sections with role awareness
The sidebar SHALL contain navigation sections: Documents, Search, Upload, Bids, and Admin. The Admin section SHALL only be visible to users with `role: "admin"`. A Legacy section SHALL provide access to deprecated pages (Home, Browse, Companies, Persons).

#### Scenario: Admin nav hidden for non-admin
- **WHEN** the authenticated user has role "editor" or "viewer"
- **THEN** the Admin navigation section is not rendered in the sidebar

#### Scenario: Admin nav visible for admin
- **WHEN** the authenticated user has role "admin"
- **THEN** the Admin navigation section is visible in the sidebar

#### Scenario: Legacy section provides access to old pages
- **WHEN** user expands the Legacy section in the sidebar
- **THEN** navigation items for Home, Browse, Companies, and Persons pages are available

### Requirement: Page state management via useState
Navigation SHALL use the existing `useState<Page>` pattern. The `Page` type SHALL be extended to include all new pages: `'documents' | 'search' | 'upload' | 'bids' | 'bid-detail' | 'admin-users' | 'admin-audit' | 'expiry' | 'home' | 'browse' | 'companies' | 'persons'`.

#### Scenario: Clicking a nav item changes the active page
- **WHEN** user clicks a navigation item (e.g., "Bids")
- **THEN** the page state updates to the corresponding page value and the main content area renders the matching page component

### Requirement: v2 API service layer
A new `services/api-v2.ts` file SHALL provide typed functions for all v2 API endpoints. It SHALL use the same auth token and error handling pattern as the existing `api.ts`. Legacy `api.ts` SHALL remain unchanged.

#### Scenario: v2 API functions use auth token
- **WHEN** any v2 API function is called
- **THEN** it includes the Bearer token from localStorage in the Authorization header

#### Scenario: v2 API handles 401 unauthorized
- **WHEN** a v2 API call returns 401
- **THEN** the token is cleared from localStorage and the user is redirected to login

### Requirement: TypeScript types for v2 API
A new `types/dms.ts` file SHALL define TypeScript interfaces for all v2 API response shapes: Folder, DmsDocument, Revision, DmsFile, Entity, Tag, DocType, BidProject, BidRequirement, BidTeamMember, BidDocument, AuditLog, User (admin).

#### Scenario: Types match API response shapes
- **WHEN** a v2 API response is received
- **THEN** the response data conforms to the corresponding TypeScript interface without type errors

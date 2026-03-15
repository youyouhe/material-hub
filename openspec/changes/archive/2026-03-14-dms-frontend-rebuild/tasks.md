## 1. Foundation: Types and API Service

- [x] 1.1 Create `frontend/src/types/dms.ts` with TypeScript interfaces for all v2 API response shapes (Folder, DmsDocument, Revision, DmsFile, Entity, Tag, DocType, BidProject, BidRequirement, BidTeamMember, BidDocument, AuditLog, User)
- [x] 1.2 Create `frontend/src/services/api-v2.ts` with typed API functions for folders, documents, search, upload, entities, tags, doc-types, expiry, bids, bid-requirements, admin, and audit endpoints
- [x] 1.3 Update Vite dev proxy config if needed to forward `/api/v2/` requests to backend

## 2. Layout Shell and Navigation

- [x] 2.1 Extend Page type in App.tsx to include all new pages: documents, search, upload, bids, bid-detail, admin-users, admin-audit, admin-migrate, expiry, plus legacy pages
- [x] 2.2 Create `frontend/src/components/Sidebar.tsx` with collapsible sidebar, nav sections (Documents, Search, Upload, Bids, Admin, Legacy), and role-aware visibility
- [x] 2.3 Create `frontend/src/components/FolderTree.tsx` that fetches folders from v2 API and renders a nested tree with expand/collapse and click-to-filter
- [x] 2.4 Refactor App.tsx layout: replace top nav bar with Sidebar + main content area, wire page state to sidebar nav clicks and folder tree selection

## 3. Document Pages

- [x] 3.1 Create `frontend/src/pages/DocumentsPage.tsx` with paginated document table, status/doc-type/folder filters, and column display (title, type, status, entity, expiry, updated)
- [x] 3.2 Create `frontend/src/components/DocumentDetailPanel.tsx` as a slide-over panel showing document metadata, revision history, entity links, tags, and lock status
- [x] 3.3 Wire DocumentsPage row click to open DocumentDetailPanel with document data fetched from `GET /api/v2/documents/{id}`
- [x] 3.4 Add edit controls to DocumentDetailPanel for editor/admin roles (inline edit title, doc_type, folder, tags, entities) calling `PATCH /api/v2/documents/{id}`

## 4. Upload Page

- [x] 4.1 Create `frontend/src/pages/UploadPageV2.tsx` with file upload form calling `POST /api/v2/upload` and upload queue display from `GET /api/v2/upload/queue`
- [x] 4.2 Add approve/reject actions to upload queue items (approve with metadata form, reject with confirmation)

## 5. Search Page

- [x] 5.1 Create `frontend/src/pages/SearchPage.tsx` with search input, results display from `GET /api/v2/search`, highlighted snippets, and click-to-open document detail

## 6. Expiry Dashboard

- [x] 6.1 Create `frontend/src/pages/ExpiryPage.tsx` with grouped expiry display (expired, <30 days, <90 days) from `GET /api/v2/expiry`, click-to-open document detail

## 7. Bid Management Pages

- [x] 7.1 Create `frontend/src/pages/BidsPage.tsx` with bid project list, status filter, text search, and requirement progress bars from `GET /api/v2/bids`
- [x] 7.2 Create `frontend/src/pages/BidDetailPage.tsx` with project info display, status badge with transition actions, and team member list
- [x] 7.3 Create `frontend/src/components/BidChecklist.tsx` rendering requirements checklist from `GET /api/v2/bids/{id}/checklist` with fulfillment indicators and progress summary
- [x] 7.4 Add document linking UI to BidChecklist: "Add Document" button showing auto-match suggestions from `/suggestions` endpoint and manual search/link
- [x] 7.5 Create bid project create/edit form with fields (name, bid_number, buyer, budget, deadline, description) calling POST/PATCH bid endpoints
- [x] 7.6 Add team member management UI (add entity+role, remove member) to BidDetailPage
- [x] 7.7 Add bulk requirement creation from category UI to BidDetailPage

## 8. Admin Pages

- [x] 8.1 Create `frontend/src/pages/AdminUsersPage.tsx` with user list table, create user form, role update dropdown, and status toggle from `GET/POST/PATCH /api/v2/admin/users`
- [x] 8.2 Create `frontend/src/pages/AdminAuditPage.tsx` with audit log table, action/resource-type filters, pagination from `GET /api/v2/audit/logs`
- [x] 8.3 Create `frontend/src/pages/AdminMigratePage.tsx` with migration status display and trigger buttons from `/api/v2/admin/migrate/` endpoints

## 9. Integration and Polish

- [x] 9.1 Wire all new pages into App.tsx page renderer (switch statement mapping Page values to components)
- [x] 9.2 Add toast notifications for all mutation operations (create, update, delete, approve, reject) using react-hot-toast
- [x] 9.3 Add loading states and empty states for all list/table pages
- [x] 9.4 Verify role-based UI: viewer sees read-only, editor sees edit controls, admin sees admin section

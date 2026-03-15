## Why

The frontend is frozen at the legacy API layer — it only uses `/api/` endpoints (materials, documents, companies, persons, smart-import). Phases 1-5 built a complete DMS backend with v2 APIs for folders, documents with revisions, entities, tags, doc types, search, upload queue, expiry tracking, RBAC, audit logs, and bid project management. None of these are exposed to users yet. The frontend needs to be rebuilt to consume the v2 APIs and provide a proper document management experience with bid project tracking.

## What Changes

- New v2 API service layer (`api-v2.ts`) with typed clients for all DMS endpoints: folders, documents, entities, tags, doc types, search, upload, bids, requirements, admin, audit
- New TypeScript type definitions for all v2 API response shapes
- Sidebar-based navigation with folder tree (file cabinet) replacing the flat tab bar
- Document list/detail pages consuming v2 documents API with revision history, entity links, tags, and lock status
- Upload page rewritten to use v2 upload flow (DMS upload → review queue → approve/reject)
- Folder browser with tree navigation and document filtering
- Search page using v2 FTS5 search endpoint
- Bid project management pages: list, detail with requirements/checklist, team management
- Admin pages: user management, audit log viewer
- Expiry dashboard using v2 expiry API
- Legacy pages (HomePage, BrowsePage, CompaniesPage, PersonsPage) retained but deprecated — accessible via "Legacy" nav section for transition period
- Role-aware UI: hide admin features from non-admin users, disable write actions for viewers

## Capabilities

### New Capabilities
- `dms-navigation`: Sidebar layout with folder tree, search bar, and role-aware navigation replacing the flat tab bar
- `dms-document-ui`: Document list, detail, revision history, entity/tag management, and upload flow using v2 APIs
- `dms-bid-ui`: Bid project list, detail with requirements checklist, team management, document linking, and auto-match UI
- `dms-admin-ui`: User management panel and audit log viewer for admin users

### Modified Capabilities

## Impact

- All files under `frontend/src/` — new pages, components, services, types
- No backend changes — purely frontend consuming existing v2 APIs
- `frontend/package.json` may get new deps (e.g., react-router if needed for deep linking)
- Legacy pages preserved but demoted in navigation
- Vite dev server proxy config may need update for v2 API paths

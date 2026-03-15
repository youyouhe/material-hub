## Context

The current frontend is a React + Vite SPA using Tailwind CSS, lucide-react icons, react-hot-toast, and clsx. No router library — navigation is tab-based via state (`useState<Tab>`). All API calls go through `services/api.ts` using the legacy `/api/` endpoints. The backend now has 15+ v2 routers under `/api/v2/` that the frontend doesn't consume at all.

The frontend stack is lightweight and effective. The rebuild keeps React + Vite + Tailwind but restructures the layout and adds v2 API consumption.

## Goals / Non-Goals

**Goals:**
- Expose all DMS v2 functionality (folders, documents, search, upload, bids) through the UI
- Sidebar-based layout with folder tree for document navigation
- Bid project management with checklist/readiness dashboard
- Admin panel for user and audit log management
- Role-aware UI (viewer/editor/admin)
- Keep the existing stack (React, Vite, Tailwind, lucide-react) — no framework migration

**Non-Goals:**
- No React Router / client-side routing — keep the `useState` tab pattern (simple, works for SPA)
- No state management library (Redux, Zustand) — keep local state and prop drilling
- No SSR or Next.js migration
- No mobile-responsive redesign (desktop-first, basic responsive)
- No i18n framework — keep hardcoded Chinese strings
- No unit tests for components (integration tested via manual QA)

## Decisions

### 1. Keep tab-based navigation via useState, add sidebar

Extend the current pattern: `type Page = 'documents' | 'search' | 'upload' | ... | 'legacy-home' | ...`. Replace the top nav bar with a collapsible sidebar containing: folder tree, main nav sections (documents, search, upload, bids, admin), and a legacy section. The main content area renders the active page.

**Alternative considered**: React Router with URL-based routing. Rejected — adds complexity (history, lazy loading, route guards) for a tool that's primarily used as a single-tab dashboard. The useState pattern is simple and already proven in this codebase.

### 2. Separate v2 API service file

Create `services/api-v2.ts` for all v2 endpoints rather than adding to `api.ts`. This avoids conflicts with legacy code and makes the migration boundary clear. Both `api.ts` (legacy) and `api-v2.ts` (DMS) coexist. Legacy pages keep using `api.ts`.

### 3. Folder tree as primary document navigation

The sidebar shows the folder hierarchy (from `GET /api/v2/folders`). Clicking a folder filters the document list. This mirrors file cabinet UX (NetSuite inspiration). A "All Documents" option at the top shows everything.

### 4. Inline document detail panel (not a separate page)

Clicking a document in the list opens a detail panel (right side or modal) showing metadata, revision history, entity links, tags, and lock status. This avoids page transitions and keeps context.

### 5. Bid management as a top-level section

Bid projects get their own nav section with: list view, detail view (with requirements checklist), and team management. The bid detail page shows a checklist-style UI with requirement fulfillment status and auto-match suggestions.

### 6. Admin section gated by role

The admin nav item only appears for users with `role: "admin"`. It contains user management and audit log viewer sub-pages. The user's role is stored in auth state after login (the login response already includes `user.role`).

### 7. Phased implementation: foundation → pages → integration

Build in order: (1) API service + types, (2) layout shell with sidebar, (3) core DMS pages (folders, documents, upload), (4) bid pages, (5) admin pages, (6) legacy bridge. This ensures each layer builds on the previous one.

## Risks / Trade-offs

- **[Risk] Large surface area** → Mitigation: Task breakdown is granular. Each page is independently implementable and testable.

- **[Trade-off] No client-side routing means no deep linking / back button** → Acceptable for an internal tool. Users don't share URLs to specific documents.

- **[Trade-off] Legacy pages retained increases bundle size** → Minimal impact. They'll be removed in a future cleanup once all users have migrated.

- **[Risk] Folder tree performance with many folders** → Mitigation: The seed data has ~16 folders. Lazy-loading children is unnecessary at this scale.

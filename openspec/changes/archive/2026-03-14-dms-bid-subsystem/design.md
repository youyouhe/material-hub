## Context

MaterialHub has a fully functional DMS core (Phases 1-4): Folder hierarchy, DmsDocument with revisions/files, DocType with JSON metadata schemas, Entity (org/person), Tags, FTS5 search, RBAC, audit logging, and document locking. The legacy system (`Material`, `Document`, `Company`, `Person`) still runs in parallel for the old frontend.

The original purpose of MaterialHub was bid-material management — helping users prepare bid/procurement responses by organizing credentials, certificates, and project references. Phase 5 reintroduces this domain logic as a structured subsystem on top of the DMS core, rather than as flat material lists.

## Goals / Non-Goals

**Goals:**
- Model bid projects as first-class entities with lifecycle tracking
- Track document requirements per bid and link them to existing DMS documents
- Provide readiness/checklist views showing what's complete vs missing
- Auto-suggest matching documents from the DMS based on doc_type
- Assign team members (from Entity model) to bid projects with roles
- Auto-create a dedicated folder per bid project
- Bridge legacy data for users transitioning from the old frontend

**Non-Goals:**
- Full bid response authoring/document generation (that's BidSmart's job)
- Approval workflows for bid submissions (simple status transitions suffice)
- Financial/accounting integration (budget is informational only)
- Notification/email system for deadlines
- Real-time collaboration features

## Decisions

### 1. Bid models in DmsBase (same database)

All bid tables use the existing `DmsBase` declarative base and live in `dms_models.py`. They share the same SQLite database as DMS tables. This avoids cross-database joins and keeps the system simple.

**Alternative considered**: Separate database for bid data. Rejected because bid entities have direct foreign keys to DmsDocument, Folder, Entity, and DocType — cross-database joins aren't possible in SQLite.

### 2. Bid project lifecycle as simple status string

Status values: `planning` → `active` → `submitted` → `won`/`lost`/`cancelled`. Stored as a string column with transition validation (same pattern as `DmsDocument.can_transition_to()`).

**Alternative considered**: State machine library. Rejected — the transitions are simple enough that a dict-based validation (like `VALID_STATUS_TRANSITIONS`) is sufficient and consistent with existing patterns.

### 3. Requirements linked to DocType for auto-matching

Each `BidRequirement` has an optional `doc_type_id` field. When set, the auto-match API queries `DmsDocument` for active documents with that doc_type_id and relevant entity links. This leverages existing classification.

**Alternative considered**: Free-text matching with FTS5 search. Too imprecise for requirement fulfillment — doc_type provides reliable structural matching.

### 4. BidDocument as explicit junction table

`BidDocument` links `BidRequirement` → `DmsDocument` with a fulfillment status (pending/linked/verified). This is separate from the requirement itself because one requirement might be fulfilled by different documents across different bid versions, and we want to track which specific document was used.

### 5. Two routers: v2_bids.py and v2_bid_requirements.py

Split by concern: `v2_bids.py` handles project CRUD, lifecycle, team members, and high-level views. `v2_bid_requirements.py` handles requirement CRUD, document linking, auto-match, and checklist/readiness.

**Alternative considered**: Single router. Rejected because bid projects and their requirements have distinct audiences and operations — separating them keeps each file focused and under ~300 lines.

### 6. Auto-create folder on bid project creation

When creating a bid project, automatically create a subfolder under `/投标文件/进行中/` (or `/投标文件/已归档/` when status transitions to terminal). Store `folder_id` on the bid project.

### 7. Legacy bridge as a lightweight migration utility

A one-time migration script (not a persistent compatibility layer) that maps legacy `Company` → `Entity`, `Person` → `Entity`, `Material` → `DmsDocument` for any materials that were part of bid activities. Exposed as an admin-only API endpoint, not an automatic process.

## Risks / Trade-offs

- **[Risk] Orphaned bid documents when DMS documents are deleted** → Mitigation: BidDocument records use soft references (no CASCADE delete). The checklist API checks if linked documents still exist and marks missing ones.

- **[Risk] Auto-match may suggest irrelevant documents** → Mitigation: Auto-match filters by doc_type AND entity links (same company). Results are suggestions only — user must explicitly link.

- **[Risk] Legacy bridge data quality** → Mitigation: Bridge is admin-only, one-shot, and produces a report of what was migrated. Users review and correct in the DMS UI.

- **[Trade-off] No real-time deadline notifications** → Acceptable for Phase 5. The checklist API returns deadline proximity, and the frontend can render warnings. Push notifications are a future enhancement.

- **[Trade-off] SQLite single-writer limitation with bid + DMS tables in same DB** → WAL mode already handles this for the existing workload. Bid operations are low-frequency compared to document operations.

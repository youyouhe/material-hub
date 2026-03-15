## Why

MaterialHub was originally a bid-material management tool (legacy `Material`, `Document`, `Company`, `Person` models). Phases 1-4 rebuilt the core as a proper DMS (Folder, DmsDocument, Revision, DmsFile, Entity, DocType, Tag, AuditLog). The legacy models still serve the old frontend, but there is no structured way to manage **bid projects** — the core business activity that ties documents, personnel, and companies together. Users need to track which bid they're preparing, what documents/credentials are required, which ones are ready vs missing, and assemble final bid packages. This phase bridges the DMS core back to the domain that originally motivated the tool.

## What Changes

- New `BidProject` model representing a single bid/procurement opportunity, with metadata (project name, bid number, buyer, deadline, budget, status, result)
- New `BidRequirement` model representing a specific document/credential requirement within a bid (e.g., "需要营业执照", "需要ISO9001证书"), linked to doc_type for auto-matching
- New `BidTeamMember` model linking Entity (person) to a BidProject with a role (项目经理, 技术负责人, etc.)
- New `BidDocument` junction model linking a BidProject requirement to an actual DmsDocument, tracking fulfillment status
- Bid project lifecycle: planning -> active -> submitted -> won/lost/cancelled
- Requirement fulfillment tracking: each requirement can be pending/linked/verified/missing
- Auto-match API that suggests existing DMS documents for unfulfilled requirements based on doc_type and entity links
- Bid checklist/readiness API showing overall completion percentage and missing items
- Dedicated folder auto-creation per bid project (under `/投标文件/`)
- All bid write operations protected by RBAC (`require_role("editor")`) and audit-logged

## Capabilities

### New Capabilities
- `bid-projects`: CRUD for bid projects with lifecycle management (planning/active/submitted/won/lost/cancelled), team member assignment, and dedicated folder creation
- `bid-requirements`: Document requirement tracking per bid — define what's needed, link to existing DMS documents, auto-match suggestions, and readiness/checklist reporting
- `bid-legacy-bridge`: Migration helpers and compatibility endpoints to bridge legacy Material/Company/Person data into the new bid subsystem

### Modified Capabilities

## Impact

- New tables: `dms_bid_projects`, `dms_bid_requirements`, `dms_bid_team_members`, `dms_bid_documents`
- New routers: `v2_bids.py`, `v2_bid_requirements.py`
- Modified: `dms_models.py` (new models), `main.py` (register routers), `seed_data.py` (bid-related doc types)
- Existing DMS APIs unchanged — bid subsystem is purely additive
- Legacy APIs (`/api/materials`, `/api/documents`) remain untouched

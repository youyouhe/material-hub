## Context

MaterialHub is a bid material management tool built with FastAPI + SQLAlchemy + SQLite (backend) and React + TypeScript (frontend). The current data model centers around a `Material` table that conflates logical documents with physical image files. Classification relies on hardcoded keyword matching in Python. The system serves a small user base preparing bid documents, with data volume currently low enough to allow a clean-break redesign.

The goal is to rebuild the data layer as a proper DMS (Document Management System) foundation, drawing on concepts from NetSuite File Cabinet and industry DMS products (M-Files, SharePoint). Bid material management becomes a subsystem of the broader DMS.

Current schema: `User`, `SessionToken`, `Company`, `Person`, `Document` (upload batch), `Material` (image record), `PendingReview`, `MaterialVersion`.

## Goals / Non-Goals

**Goals:**
- Design a normalized, extensible data model that supports hierarchical folders, configurable document types, document versioning, and flexible entity relationships
- Enable new document types and metadata fields to be added without code changes (via DocType configuration)
- Migrate all existing data from legacy tables to the new schema
- Provide clean CRUD APIs for all new models
- Preserve BidSmart material search compatibility during transition

**Non-Goals:**
- Frontend rebuild (deferred to Phase 6)
- Smart import pipeline adaptation (deferred to Phase 2)
- Full-text search indexing (deferred to Phase 3)
- RBAC / permissions system (deferred to Phase 4)
- Workflow / state machine engine (deferred to Phase 4)
- File storage migration to S3 or other cloud storage

## Decisions

### 1. Unified Entity model vs. separate Company/Person tables

**Decision**: Single `Entity` table with `entity_type` discriminator and JSON `attributes` column.

**Rationale**: The current Company and Person tables have overlapping patterns (name, created_at, relationships to materials). A unified Entity model with type-specific attributes in JSON is more extensible — adding a new entity type (e.g., "department", "project") requires no schema migration. Parent-child relationships (person belongs to company) use a self-referential `parent_id`.

**Alternative considered**: Keep separate tables with a polymorphic association. Rejected because it adds complexity for little benefit at this scale, and SQLite doesn't enforce polymorphic constraints anyway.

### 2. Dynamic metadata via JSON column vs. EAV (Entity-Attribute-Value)

**Decision**: `DocType.metadata_schema` defines the field schema as JSON; `Document.metadata` stores the actual values as JSON. No EAV pattern.

**Rationale**: EAV tables are notoriously difficult to query and maintain. JSON columns in SQLite (via json_extract) provide adequate query capability for our scale. The schema definition in DocType serves as documentation and validation template. This is the same approach used by headless CMS systems (Strapi, Directus).

**Alternative considered**: EAV with attribute/value tables. Rejected for query complexity. Also considered: separate tables per doc type — rejected for migration burden when adding types.

### 3. Folder hierarchy: materialized path vs. nested sets vs. adjacency list

**Decision**: Adjacency list (`parent_id`) with a materialized `path` column (e.g., `/company-qualifications/business-license/`).

**Rationale**: Adjacency list is simple for inserts and moves. Materialized path enables efficient subtree queries (`WHERE path LIKE '/company-qualifications/%'`) without recursive CTEs. The path column is denormalized but acceptable for a folder tree that changes infrequently. Nested sets are complex to maintain on insert/delete.

**Alternative considered**: Pure adjacency list with recursive CTEs — works but SQLite recursive CTE performance degrades on deep trees. Nested sets — too complex for the benefit.

### 4. File model: separate table vs. embedded in Revision

**Decision**: Separate `File` table linked to `Revision` with a `file_type` discriminator.

**Rationale**: A single document revision may have multiple associated files: the original upload (PDF), extracted page images, thumbnails, and OCR text files. A separate File table cleanly models this 1:N relationship. The `file_type` field (original, thumbnail, extracted_page, ocr_result) distinguishes file roles.

### 5. Migration strategy: in-place alter vs. new tables + copy

**Decision**: Create all new tables alongside existing ones, run a Python migration script that copies and transforms data, then drop legacy tables.

**Rationale**: This is safer than in-place ALTER TABLE operations. The migration script can be tested independently, and rollback means simply dropping the new tables. SQLite's ALTER TABLE support is limited anyway.

**Migration mapping:**
- `Company` → `Entity(entity_type='org')` with attributes JSON
- `Person` → `Entity(entity_type='person', parent_id=mapped_company_entity_id)`
- `Document` (legacy) → used to reconstruct `Document` (new) + `Folder` placement
- `Material` → `Document` (new) + `Revision` + `File` records; metadata extracted from material_type/extracted_json
- `MaterialVersion` → `Revision` records with version_number preserved
- `PendingReview` → kept as-is temporarily (will be redesigned in Phase 2 with new upload pipeline)

### 6. API design: REST resource naming

**Decision**: New API endpoints under `/api/v2/` prefix. Legacy `/api/materials`, `/api/companies`, `/api/persons` preserved as thin compatibility shims.

**Rationale**: Versioned API prefix allows gradual migration. The v2 endpoints follow standard REST conventions:
- `/api/v2/folders/` — folder tree CRUD
- `/api/v2/documents/` — document CRUD with filtering
- `/api/v2/documents/{id}/revisions/` — nested revision management
- `/api/v2/doc-types/` — document type configuration
- `/api/v2/entities/` — unified entity CRUD
- `/api/v2/tags/` — tag management

### 7. Seed data approach

**Decision**: Python seed script that runs on first startup (when folders table is empty), creating default folder structure and document types.

**Rationale**: Consistent with current pattern of `_create_default_admin()`. Seed data includes:
- Default folder tree: company qualifications, personnel qualifications, project records, bid documents (with subfolders)
- Default DocTypes: business_license, qualification_cert, iso_cert, honor_award, id_card, education_cert, professional_cert, contract, acceptance_report, bid_document
- Each DocType includes its metadata_schema defining the fields relevant to that type

## Risks / Trade-offs

**[JSON metadata query performance]** → At current scale (hundreds to low thousands of documents), SQLite JSON functions are adequate. If scale grows significantly, consider migrating to PostgreSQL with native JSONB indexing. Monitor query times.

**[Migration data loss]** → The migration script will be run once on existing data. Risk: unmapped fields or edge cases. Mitigation: migration script logs all skipped/failed records; manual review before dropping legacy tables. Keep a database backup.

**[Frontend downtime during Phase 1]** → The existing frontend will break against new APIs. Mitigation: Legacy API shims preserve basic functionality. Full frontend rebuild is Phase 6. For the transition period, API consumers (BidSmart skills) use the compatibility endpoints.

**[Over-abstraction risk]** → Building a "generic DMS" when primary use case is bid materials. Mitigation: Design is generic but implementation scope is minimal — only build what's needed for bid materials in Phase 1. DocType and Folder are inherently simple; the abstraction cost is low.

**[JSON schema evolution]** → DocType metadata_schema may change over time. Documents created with an old schema version may have stale metadata. Mitigation: metadata is loosely validated (extra fields ignored, missing fields default to null). No strict schema enforcement initially.

## Migration Plan

1. **Backup**: Copy `data/materials.db` to `data/materials.db.backup`
2. **Create new tables**: Run SQLAlchemy `Base.metadata.create_all()` which creates new tables alongside existing ones
3. **Run migration script**: `python migrate_to_dms.py` — transforms and copies data from legacy to new tables
4. **Verify**: Script outputs migration report (counts, warnings, skipped records)
5. **Activate new API**: Switch router includes from legacy to v2 routers
6. **Drop legacy tables**: Only after verification; reversible by restoring backup
7. **Rollback**: Restore `materials.db.backup`, revert router configuration

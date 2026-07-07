## Why

MaterialHub currently operates as a flat material management tool where all documents are stored as image records (Material) in a single table with hardcoded classification logic. The system lacks hierarchical organization, configurable document types, proper version control, and flexible entity relationships. This makes it brittle to extend (adding a new material type requires code changes), difficult to navigate at scale, and unsuitable as a foundation for broader document management needs beyond bid materials. Rebuilding the core data model as a proper DMS foundation enables MaterialHub to grow from a single-purpose tool into an extensible platform where bid material management is one well-supported subsystem.

## What Changes

- **BREAKING**: Replace the `Material` table with a new `Document` + `Revision` + `File` model that separates logical documents from physical files and supports versioning
- **BREAKING**: Replace `Company` and `Person` tables with a unified `Entity` model (entity_type: org/person) using JSON attributes for type-specific fields
- **BREAKING**: Replace hardcoded material_type/section classification with a configurable `DocType` system that defines metadata schemas per document type
- Introduce `Folder` model for hierarchical file cabinet organization with materialized path for efficient tree queries
- Introduce `Tag` model and `DocumentTag` join table for flexible cross-cutting labeling
- Introduce `DocumentEntity` join table with role-based relationships (owner, issuer, subject) replacing fixed foreign keys
- Create seed data: default folder structure (company qualifications, personnel, project records, bid documents) and default document types (business license, qualification certificate, ID card, education certificate, etc.)
- Create data migration script to move existing Material/Company/Person/Document/MaterialVersion/PendingReview records into the new schema
- Provide basic CRUD API endpoints for all new models (Folder tree, Document lifecycle, DocType management, Entity management, Tag operations)
- Preserve the existing BidSmart material search API as a compatibility layer on top of new models

## Capabilities

### New Capabilities
- `folder-management`: Hierarchical folder (file cabinet) tree with CRUD operations, drag-and-drop reordering, and materialized path queries
- `document-lifecycle`: Core document model with create, read, update, status transitions (draft/active/expired/archived), and folder assignment
- `revision-management`: Document versioning with revision history, current version tracking, and change notes
- `file-storage`: Physical file management supporting multiple file types per revision (original, thumbnail, extracted page, OCR result)
- `doc-type-system`: Configurable document types with dynamic JSON metadata schemas, category grouping, and seed types for bid materials
- `entity-model`: Unified organization/person entity model with JSON attributes, parent-child relationships, and role-based document linking
- `tag-system`: Flexible document tagging with colored tags, bulk operations, and tag-based filtering
- `data-migration`: One-time migration from legacy schema (Material, Company, Person, Document, MaterialVersion) to new DMS models with rollback support

### Modified Capabilities

(none - no existing specs)

## Impact

- **Database**: Complete schema redesign. All existing tables (materials, documents, companies, persons, material_versions, pending_reviews) will be replaced or restructured. Migration script required.
- **Backend API**: All `/api/materials/*`, `/api/documents/*`, `/api/companies/*`, `/api/persons/*` endpoints will be replaced with new DMS endpoints. The `/api/smart-import/*` endpoints will need adaptation in a subsequent phase.
- **Frontend**: Will need full rebuild in a subsequent phase (Phase 6). During Phase 1, the frontend will be non-functional against the new API.
- **BidSmart Integration**: The material search API used by bid skills must be preserved as a compatibility shim until the bid subsystem is rebuilt (Phase 5).
- **Dependencies**: No new Python dependencies required. SQLAlchemy and SQLite remain. JSON schema validation may use built-in `jsonschema` or simple manual validation.
- **File Storage**: Physical file storage layout unchanged (data/files/, data/images/). File records will now reference storage paths through the new File model.

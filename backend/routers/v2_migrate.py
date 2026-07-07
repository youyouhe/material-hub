"""Legacy data migration endpoints (admin-only)."""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter

from database import get_session, User, Company, Person, Material, MaterialVersion, PendingReview
from dms_models import (
    get_dms_session, Entity, DmsDocument, Revision, DmsFile,
    DocType, DocumentEntity, Folder, DmsUser, EntityRelation,
)
from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_migrate")

router = APIRouter(prefix="/api/v2/admin/migrate", tags=["admin-migrate"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))

# Map legacy material_type to DMS doc_type code
MATERIAL_TYPE_TO_DOC_CODE = {
    "license": "business-license",
    "qualification": "qualification-cert",
    "iso_cert": "iso-cert",
    "honor_award": "honor-award",
    "id_card": "id-card",
    "education": "education-cert",
    "certificate": "professional-cert",
    "legal_person_cert": "business-license",
}

# Map material.section free-text keywords to DMS folder paths
# Order matters: more specific entries first
SECTION_TO_FOLDER_PATH = {
    "营业执照": "/公司资质/营业执照",
    "资质证书": "/公司资质/资质证书",
    "iso认证":  "/公司资质/ISO认证",
    "iso":      "/公司资质/ISO认证",
    "荣誉奖项": "/公司资质/荣誉奖项",
    "授权文件": "/公司资质/授权文件",
    "身份证件": "/人员资质/身份证件",
    "身份证":   "/人员资质/身份证件",
    "学历证书": "/人员资质/学历证书",
    "学历":     "/人员资质/学历证书",
    "职称":     "/人员资质/职称证书",
    "合同":     "/业绩材料/合同",
    "发票":     "/业绩材料/发票",
    "验收报告": "/业绩材料/验收报告",
}


@router.post("/users", dependencies=[require_role("admin")])
async def migrate_users():
    """Migrate legacy User records to DmsUser."""
    with get_session() as legacy:
        users = legacy.query(User).all()
        # Extract all data before session closes (avoid DetachedInstanceError)
        user_data = [
            {
                "id": u.id,
                "username": u.username,
                "password_hash": u.password_hash,
                "role": u.role or "editor",
                "created_at": u.created_at,
                "last_login": u.last_login,
            }
            for u in users
        ]

    created = 0
    skipped = 0
    with get_dms_session() as dms:
        for ud in user_data:
            existing = dms.query(DmsUser).filter(
                DmsUser.username == ud["username"],
            ).first()
            if existing:
                # Back-fill legacy_user_id if missing
                if not existing.legacy_user_id:
                    existing.legacy_user_id = ud["id"]
                skipped += 1
                continue

            dms_user = DmsUser(
                username=ud["username"],
                password_hash=ud["password_hash"],
                role=ud["role"],
                created_at=ud["created_at"],
                last_login=ud["last_login"],
                legacy_user_id=ud["id"],
            )
            dms.add(dms_user)
            created += 1

    return {"created": created, "skipped": skipped, "total": len(user_data)}


@router.get("/status", dependencies=[require_role("admin")])
async def migration_status():
    """Count legacy records vs migrated DMS records."""
    with get_session() as legacy:
        user_count = legacy.query(User).count()
        company_count = legacy.query(Company).count()
        person_count = legacy.query(Person).count()
        material_count = legacy.query(Material).count()
        version_count = legacy.query(MaterialVersion).count()

    with get_dms_session() as dms:
        dms_user_count = dms.query(DmsUser).count()
        entity_org_count = dms.query(Entity).filter(Entity.entity_type == "org").count()
        entity_person_count = dms.query(Entity).filter(Entity.entity_type == "person").count()
        doc_count = dms.query(DmsDocument).count()
        revision_count = dms.query(Revision).count()
        relation_count = dms.query(EntityRelation).count()

    return {
        "users": {"legacy": user_count, "migrated": dms_user_count},
        "companies": {"legacy": company_count, "migrated": entity_org_count},
        "persons": {"legacy": person_count, "migrated": entity_person_count},
        "materials": {"legacy": material_count, "migrated": doc_count},
        "material_versions": {"legacy": version_count, "migrated": revision_count},
        "entity_relations": {"migrated": relation_count},
    }


@router.post("/companies", dependencies=[require_role("admin")])
async def migrate_companies():
    """Migrate legacy Company records to Entity (entity_type='org')."""
    with get_session() as legacy:
        companies = legacy.query(Company).all()
        company_data = [
            {
                "name": c.name,
                "legal_person": c.legal_person,
                "credit_code": c.credit_code,
                "address": c.address,
            }
            for c in companies
        ]

    created = 0
    skipped = 0
    with get_dms_session() as dms:
        for cd in company_data:
            existing = dms.query(Entity).filter(
                Entity.entity_type == "org",
                Entity.name == cd["name"],
            ).first()
            if existing:
                # Back-fill credit_code into the dedicated column if it was empty
                if not existing.credit_code and cd.get("credit_code"):
                    existing.credit_code = cd["credit_code"]
                skipped += 1
                continue

            attrs = {}
            if cd["legal_person"]:
                attrs["legal_person"] = cd["legal_person"]
            if cd["credit_code"]:
                attrs["credit_code"] = cd["credit_code"]
            if cd["address"]:
                attrs["address"] = cd["address"]

            entity = Entity(
                entity_type="org",
                name=cd["name"],
                attributes=json.dumps(attrs, ensure_ascii=False) if attrs else None,
                credit_code=cd.get("credit_code"),
            )
            dms.add(entity)
            created += 1

    return {"created": created, "skipped": skipped, "total": len(company_data)}


@router.post("/persons", dependencies=[require_role("admin")])
async def migrate_persons():
    """Migrate legacy Person records to Entity (entity_type='person')."""
    with get_session() as legacy:
        persons = legacy.query(Person).all()
        person_data = [
            {
                "name": p.name,
                "id_number": p.id_number,
                "education": p.education,
                "position": p.position,
                "company_id": p.company_id,
            }
            for p in persons
        ]

    created = 0
    skipped = 0
    with get_dms_session() as dms:
        for pd in person_data:
            existing = dms.query(Entity).filter(
                Entity.entity_type == "person",
                Entity.name == pd["name"],
            ).first()
            if existing:
                # Back-fill company_id_legacy if missing
                if not existing.company_id_legacy and pd.get("company_id"):
                    existing.company_id_legacy = pd["company_id"]
                skipped += 1
                continue

            attrs = {}
            if pd["id_number"]:
                attrs["id_number"] = pd["id_number"]
            if pd["education"]:
                attrs["education"] = pd["education"]
            if pd["position"]:
                attrs["position"] = pd["position"]
            if pd["company_id"]:
                attrs["legacy_company_id"] = pd["company_id"]

            entity = Entity(
                entity_type="person",
                name=pd["name"],
                attributes=json.dumps(attrs, ensure_ascii=False) if attrs else None,
                company_id_legacy=pd.get("company_id"),
            )
            dms.add(entity)
            created += 1

    return {"created": created, "skipped": skipped, "total": len(person_data)}


@router.post("/materials", dependencies=[require_role("admin")])
async def migrate_materials():
    """Migrate legacy Material records to DmsDocument + Revision + DmsFile."""
    with get_session() as legacy:
        materials = legacy.query(Material).all()
        mat_data = []
        for m in materials:
            mat_data.append({
                "id": m.id,
                "title": m.title,
                "section": m.section or "",
                "material_type": m.material_type,
                "image_filename": m.image_filename,
                "image_path": m.image_path,
                "file_size": m.file_size,
                "file_hash": m.file_hash,
                "expiry_date": m.expiry_date,
                "company_id": m.company_id,
                "person_id": m.person_id,
                "ocr_text": m.ocr_text,
                "extracted_json": m.extracted_json,
                "ocr_status": m.ocr_status,
                "ocr_error": m.ocr_error,
                "ocr_processed_at": (
                    m.ocr_processed_at.isoformat() if m.ocr_processed_at else None
                ),
            })

    created = 0
    skipped = 0
    errors = []

    with get_dms_session() as dms:
        # Preload lookups
        doc_types = {dt.code: dt for dt in dms.query(DocType).all()}
        folder_map = {f.path: f.id for f in dms.query(Folder).all()}

        company_names = {}
        person_names = {}
        with get_session() as legacy:
            for c in legacy.query(Company).all():
                company_names[c.id] = c.name
            for p in legacy.query(Person).all():
                person_names[p.id] = p.name

        for md in mat_data:
            # Idempotency: prefer file_hash dedup; fall back to _legacy_id in meta_json
            if md["file_hash"]:
                existing_file = dms.query(DmsFile).filter(
                    DmsFile.file_hash == md["file_hash"]
                ).first()
                if existing_file:
                    skipped += 1
                    continue
            else:
                existing_doc = dms.query(DmsDocument).filter(
                    DmsDocument.meta_json.like(f'%"_legacy_id": {md["id"]}%')
                ).first()
                if existing_doc:
                    skipped += 1
                    continue

            # Determine doc_type
            doc_type_id = None
            if md["material_type"]:
                code = MATERIAL_TYPE_TO_DOC_CODE.get(md["material_type"])
                if code and code in doc_types:
                    doc_type_id = doc_types[code].id

            # Resolve folder from section text (first matching keyword wins)
            folder_id = None
            if md["section"]:
                section_lower = md["section"].strip().lower()
                for keyword, path in SECTION_TO_FOLDER_PATH.items():
                    if keyword in section_lower:
                        folder_id = folder_map.get(path)
                        break

            # Build meta_json: always store _legacy_id; preserve OCR data if present
            meta = {"_legacy_id": md["id"]}
            if md["ocr_text"] or md["ocr_status"]:
                meta["_legacy_ocr"] = {
                    "text": md["ocr_text"],
                    "status": md["ocr_status"],
                    "error": md["ocr_error"],
                    "processed_at": md["ocr_processed_at"],
                    "extracted_json": md["extracted_json"],
                }

            # Create Document
            doc = DmsDocument(
                title=md["title"],
                status="active",
                doc_type_id=doc_type_id,
                folder_id=folder_id,
                expiry_date=md["expiry_date"],
                meta_json=json.dumps(meta, ensure_ascii=False),
            )
            dms.add(doc)
            dms.flush()

            # Create Revision
            rev = Revision(
                document_id=doc.id,
                version_number=1,
                is_current=True,
            )
            dms.add(rev)
            dms.flush()

            # Create File record if image exists on disk
            image_path = Path(md["image_path"]) if md["image_path"] else None
            if image_path and image_path.exists():
                try:
                    storage_path = str(image_path.resolve().relative_to(DATA_DIR.resolve()))
                except ValueError:
                    storage_path = str(image_path)

                dms_file = DmsFile(
                    revision_id=rev.id,
                    file_type="original",
                    filename=md["image_filename"] or image_path.name,
                    storage_path=storage_path,
                    mime_type="image/png",
                    file_size=md["file_size"] or 0,
                    file_hash=md["file_hash"],
                )
                dms.add(dms_file)
            else:
                if md["image_path"]:
                    errors.append(f"File not found: {md['image_path']} (doc: {md['title']})")

            # Create entity links; log explicitly when entity not found (no silent drops)
            if md["company_id"] and md["company_id"] in company_names:
                entity = dms.query(Entity).filter(
                    Entity.entity_type == "org",
                    Entity.name == company_names[md["company_id"]],
                ).first()
                if entity:
                    dms.add(DocumentEntity(document_id=doc.id, entity_id=entity.id, role="owner"))
                else:
                    errors.append(
                        f"Company entity not found for '{md['title']}' "
                        f"(company_id={md['company_id']}); run /companies first"
                    )

            if md["person_id"] and md["person_id"] in person_names:
                entity = dms.query(Entity).filter(
                    Entity.entity_type == "person",
                    Entity.name == person_names[md["person_id"]],
                ).first()
                if entity:
                    dms.add(DocumentEntity(document_id=doc.id, entity_id=entity.id, role="subject"))
                else:
                    errors.append(
                        f"Person entity not found for '{md['title']}' "
                        f"(person_id={md['person_id']}); run /persons first"
                    )

            created += 1

    result = {"created": created, "skipped": skipped, "total": len(mat_data)}
    if errors:
        result["warnings"] = errors[:20]
    return result


@router.post("/material-versions", dependencies=[require_role("admin")])
async def migrate_material_versions():
    """Migrate legacy MaterialVersion records to DmsRevision.

    Prerequisites: run /materials first so _legacy_id mappings exist in meta_json.
    """
    with get_session() as legacy:
        versions = legacy.query(MaterialVersion).all()
        ver_data = [
            {
                "material_id": v.material_id,
                "version_number": v.version_number,
                "is_current": v.is_current,
                "relation_type": v.relation_type,
                "replaced_at": v.replaced_at,
                "replaced_reason": v.replaced_reason,
                "note": v.note,
                "created_by": v.created_by,
                "prev_material_id": v.previous_material_id,
            }
            for v in versions
        ]

    created = 0
    skipped = 0
    errors = []

    with get_dms_session() as dms:
        for vd in ver_data:
            # Find the migrated DmsDocument via _legacy_id stored in meta_json
            doc = dms.query(DmsDocument).filter(
                DmsDocument.meta_json.like(f'%"_legacy_id": {vd["material_id"]}%')
            ).first()
            if not doc:
                errors.append(
                    f"Material {vd['material_id']} not found in DMS — run /materials first"
                )
                continue

            # Skip if this version_number already exists for this document
            existing = dms.query(Revision).filter(
                Revision.document_id == doc.id,
                Revision.version_number == vd["version_number"],
            ).first()
            if existing:
                skipped += 1
                continue

            # Build change_note from legacy fields
            parts = []
            if vd["relation_type"]:
                parts.append(f"[{vd['relation_type']}]")
            if vd["note"]:
                parts.append(vd["note"])
            if vd["replaced_reason"]:
                parts.append(f"替换原因: {vd['replaced_reason']}")

            rev = Revision(
                document_id=doc.id,
                version_number=vd["version_number"],
                is_current=vd["is_current"],
                change_note=" ".join(parts) if parts else None,
                created_by=vd["created_by"],
            )
            # Override created_at with original replaced_at timestamp if available
            if vd["replaced_at"]:
                rev.created_at = vd["replaced_at"]

            # Store previous material id hint in doc meta_json
            if vd["prev_material_id"]:
                try:
                    meta = json.loads(doc.meta_json) if doc.meta_json else {}
                except (json.JSONDecodeError, TypeError):
                    meta = {}
                meta[f"_legacy_prev_id_v{vd['version_number']}"] = vd["prev_material_id"]
                doc.meta_json = json.dumps(meta, ensure_ascii=False)

            dms.add(rev)
            created += 1

    result = {"created": created, "skipped": skipped, "total": len(ver_data)}
    if errors:
        result["warnings"] = errors[:20]
    return result


@router.post("/entity-relations", dependencies=[require_role("admin")])
async def migrate_entity_relations():
    """Rebuild person→company (employed_by) relations from legacy persons.company_id.

    Uses legacy_company_id stored in Entity.attributes (from phase 0-3)
    and the dedicated company_id_legacy column on dms_entities.
    """
    with get_session() as legacy:
        persons = legacy.query(Person).filter(Person.company_id.isnot(None)).all()
        companies = legacy.query(Company).all()
        # Extract data before session closes (avoid DetachedInstanceError)
        legacy_company_names = {c.id: c.name for c in companies}
        person_data = [
            {"id": p.id, "name": p.name, "company_id": p.company_id}
            for p in persons
        ]

    created = 0
    skipped = 0
    errors = []

    with get_dms_session() as dms:
        # Preload all entities
        person_entities = {
            e.name: e for e in dms.query(Entity).filter(Entity.entity_type == "person").all()
        }
        org_entities = {
            e.name: e for e in dms.query(Entity).filter(Entity.entity_type == "org").all()
        }

        for pd in person_data:
            # Find the person's DMS entity by name
            person_entity = person_entities.get(pd["name"])
            if not person_entity:
                errors.append(f"Person entity not found for '{pd['name']}' (legacy id={pd['id']})")
                continue

            # Find the company's DMS entity
            company_name = legacy_company_names.get(pd["company_id"])
            if not company_name:
                errors.append(
                    f"Legacy company id={pd['company_id']} not found for person '{pd['name']}'"
                )
                continue

            org_entity = org_entities.get(company_name)
            if not org_entity:
                # Try by legacy_company_id in dedicated column
                org_entity = dms.query(Entity).filter(
                    Entity.entity_type == "org",
                    Entity.company_id_legacy == pd["company_id"],
                ).first()
            if not org_entity:
                errors.append(
                    f"Company entity '{company_name}' (legacy id={pd['company_id']}) "
                    f"not found for person '{pd['name']}'"
                )
                continue

            # Check if relation already exists
            existing = dms.query(EntityRelation).filter(
                EntityRelation.from_id == person_entity.id,
                EntityRelation.to_id == org_entity.id,
                EntityRelation.relation == "employed_by",
            ).first()
            if existing:
                skipped += 1
                continue

            # Create relation: person → employed_by → company
            rel = EntityRelation(
                from_id=person_entity.id,
                to_id=org_entity.id,
                relation="employed_by",
            )
            dms.add(rel)
            created += 1

    result = {"created": created, "skipped": skipped, "total": len(person_data)}
    if errors:
        result["warnings"] = errors[:20]
    return result


@router.post("/pending-reviews", dependencies=[require_role("admin")])
async def migrate_pending_reviews():
    """Migrate legacy PendingReview records (status=pending) to DMS draft documents.

    Only migrates records whose file still exists on disk.
    Preserves analysis_json and entities_json in meta_json.
    """
    with get_session() as legacy:
        reviews = legacy.query(PendingReview).filter(
            PendingReview.status == "pending"
        ).all()
        review_data = []
        for r in reviews:
            file_path = Path(r.file_path) if r.file_path else None
            exists = file_path and file_path.exists()
            review_data.append({
                "id": r.id,
                "filename": r.filename,
                "file_path": str(r.file_path) if r.file_path else None,
                "file_exists": exists,
                "file_hash": r.file_hash,
                "analysis_json": r.analysis_json,
                "entities_json": r.entities_json,
                "confidence": r.confidence,
            })

    created = 0
    skipped = 0
    errors = []

    with get_dms_session() as dms:
        for rd in review_data:
            if not rd["file_exists"]:
                skipped += 1
                continue

            file_path = Path(rd["file_path"])

            # Skip if already migrated (by file_hash)
            if rd["file_hash"]:
                existing = dms.query(DmsFile).filter(
                    DmsFile.file_hash == rd["file_hash"], DmsFile.file_type == "original"
                ).first()
                if existing:
                    skipped += 1
                    continue

            # Build meta_json from legacy analysis
            meta = {"_legacy_review_id": rd["id"], "_migrated_from": "pending_review"}
            if rd["analysis_json"]:
                try:
                    analysis = json.loads(rd["analysis_json"])
                    if analysis.get("material_type"):
                        meta["material_type"] = analysis["material_type"]
                    if analysis.get("material_name"):
                        meta["summary"] = analysis["material_name"]
                except (json.JSONDecodeError, TypeError):
                    pass

            # Determine mime type
            ext = file_path.suffix.lower()
            mime_map = {
                ".pdf": "application/pdf",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".tiff": "image/tiff",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            mime_type = mime_map.get(ext, "application/octet-stream")

            file_size = file_path.stat().st_size if file_path.exists() else 0

            # Create DMS document
            doc = DmsDocument(
                title=rd["filename"],
                status="draft",
                meta_json=json.dumps(meta, ensure_ascii=False),
            )
            dms.add(doc)
            dms.flush()

            rev = Revision(document_id=doc.id, version_number=1, is_current=True)
            dms.add(rev)
            dms.flush()

            # Copy file to DMS storage
            rev_dir = DATA_DIR / "dms_files" / str(doc.id) / str(rev.id)
            rev_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{rd['file_hash'][:8] if rd['file_hash'] else 'legacy'}_{rd['filename']}"
            storage_path = f"dms_files/{doc.id}/{rev.id}/{safe_name}"
            full_path = DATA_DIR / storage_path

            try:
                import shutil
                shutil.copy2(str(file_path), str(full_path))
            except Exception as e:
                errors.append(f"Copy failed for review {rd['id']}: {e}")
                # Remove the document + revision we just created
                dms.delete(rev)
                dms.delete(doc)
                dms.flush()
                continue

            dms_file = DmsFile(
                revision_id=rev.id,
                file_type="original",
                filename=rd["filename"],
                storage_path=storage_path,
                mime_type=mime_type,
                file_size=file_size,
                file_hash=rd["file_hash"],
            )
            dms.add(dms_file)
            created += 1

    result = {
        "created": created, "skipped": skipped,
        "skipped_reason": "file not found or already migrated",
        "total": len(review_data),
    }
    if errors:
        result["warnings"] = errors[:20]
    return result

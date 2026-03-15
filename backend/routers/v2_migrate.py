"""Legacy data migration endpoints (admin-only)."""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter

from database import get_session, Company, Person, Material
from dms_models import (
    get_dms_session, Entity, DmsDocument, Revision, DmsFile,
    DocType, DocumentEntity,
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


@router.get("/status", dependencies=[require_role("admin")])
async def migration_status():
    """Count legacy records vs migrated DMS records."""
    with get_session() as legacy:
        company_count = legacy.query(Company).count()
        person_count = legacy.query(Person).count()
        material_count = legacy.query(Material).count()

    with get_dms_session() as dms:
        entity_org_count = dms.query(Entity).filter(Entity.entity_type == "org").count()
        entity_person_count = dms.query(Entity).filter(Entity.entity_type == "person").count()
        doc_count = dms.query(DmsDocument).count()

    return {
        "companies": {"legacy": company_count, "migrated": entity_org_count},
        "persons": {"legacy": person_count, "migrated": entity_person_count},
        "materials": {"legacy": material_count, "migrated": doc_count},
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
                skipped += 1
                continue

            attrs = {}
            if pd["id_number"]:
                attrs["id_number"] = pd["id_number"]
            if pd["education"]:
                attrs["education"] = pd["education"]
            if pd["position"]:
                attrs["position"] = pd["position"]

            entity = Entity(
                entity_type="person",
                name=pd["name"],
                attributes=json.dumps(attrs, ensure_ascii=False) if attrs else None,
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
                "title": m.title,
                "material_type": m.material_type,
                "image_filename": m.image_filename,
                "image_path": m.image_path,
                "file_size": m.file_size,
                "file_hash": m.file_hash,
                "expiry_date": m.expiry_date,
                "company_id": m.company_id,
                "person_id": m.person_id,
            })

    created = 0
    skipped = 0
    errors = []

    with get_dms_session() as dms:
        # Build doc_type lookup
        doc_types = {dt.code: dt for dt in dms.query(DocType).all()}

        # Build entity name lookup for company/person matching
        # We match by looking up legacy Company/Person names
        company_names = {}
        person_names = {}
        with get_session() as legacy:
            for c in legacy.query(Company).all():
                company_names[c.id] = c.name
            for p in legacy.query(Person).all():
                person_names[p.id] = p.name

        for md in mat_data:
            # Skip if already migrated (by file_hash)
            if md["file_hash"]:
                existing = dms.query(DmsFile).filter(DmsFile.file_hash == md["file_hash"]).first()
                if existing:
                    skipped += 1
                    continue

            # Determine doc_type
            doc_type_id = None
            if md["material_type"]:
                code = MATERIAL_TYPE_TO_DOC_CODE.get(md["material_type"])
                if code and code in doc_types:
                    doc_type_id = doc_types[code].id

            # Create Document
            doc = DmsDocument(
                title=md["title"],
                status="active",
                doc_type_id=doc_type_id,
                expiry_date=md["expiry_date"],
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

            # Check if image file exists and create File record
            image_path = Path(md["image_path"]) if md["image_path"] else None
            if image_path and image_path.exists():
                # Compute storage_path relative to DATA_DIR
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
                # File missing, still create doc but note in errors
                if md["image_path"]:
                    errors.append(f"File not found: {md['image_path']} (doc: {md['title']})")

            # Create entity links
            if md["company_id"] and md["company_id"] in company_names:
                company_name = company_names[md["company_id"]]
                entity = dms.query(Entity).filter(
                    Entity.entity_type == "org",
                    Entity.name == company_name,
                ).first()
                if entity:
                    de = DocumentEntity(
                        document_id=doc.id,
                        entity_id=entity.id,
                        role="owner",
                    )
                    dms.add(de)

            if md["person_id"] and md["person_id"] in person_names:
                person_name = person_names[md["person_id"]]
                entity = dms.query(Entity).filter(
                    Entity.entity_type == "person",
                    Entity.name == person_name,
                ).first()
                if entity:
                    de = DocumentEntity(
                        document_id=doc.id,
                        entity_id=entity.id,
                        role="subject",
                    )
                    dms.add(de)

            created += 1

    result = {"created": created, "skipped": skipped, "total": len(mat_data)}
    if errors:
        result["warnings"] = errors[:20]  # Cap warnings
    return result

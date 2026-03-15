"""DMS DocType (Document Type Configuration) API endpoints."""

import json
import logging
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dms_models import get_dms_session, DocType, DmsDocument
from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_doc_types")

router = APIRouter(prefix="/api/v2/doc-types", tags=["dms-doc-types"])


class DocTypeCreate(BaseModel):
    name: str
    code: str
    category: str
    metadata_schema: Optional[Any] = None
    icon: Optional[str] = None
    description: Optional[str] = None


class DocTypeUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    metadata_schema: Optional[Any] = None
    icon: Optional[str] = None
    description: Optional[str] = None


@router.get("/")
async def list_doc_types(category: Optional[str] = Query(None)):
    """List all document types, optionally filtered by category."""
    with get_dms_session() as session:
        query = session.query(DocType)
        if category:
            query = query.filter(DocType.category == category)
        doc_types = query.order_by(DocType.category, DocType.name).all()

        # Group by category
        grouped = {}
        for dt in doc_types:
            cat = dt.category
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(dt.to_dict())

        return {"doc_types": grouped, "total": len(doc_types)}


@router.post("/", dependencies=[require_role("editor")])
async def create_doc_type(data: DocTypeCreate):
    """Create a custom document type."""
    with get_dms_session() as session:
        existing = session.query(DocType).filter(DocType.code == data.code).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"DocType with code '{data.code}' already exists")

        schema_str = None
        if data.metadata_schema is not None:
            schema_str = json.dumps(data.metadata_schema, ensure_ascii=False)

        dt = DocType(
            name=data.name,
            code=data.code,
            category=data.category,
            metadata_schema=schema_str,
            icon=data.icon,
            description=data.description,
            is_system=False,
        )
        session.add(dt)
        session.flush()
        return dt.to_dict()


@router.patch("/{doc_type_id}", dependencies=[require_role("editor")])
async def update_doc_type(doc_type_id: int, data: DocTypeUpdate):
    """Update a document type."""
    with get_dms_session() as session:
        dt = session.query(DocType).filter(DocType.id == doc_type_id).first()
        if not dt:
            raise HTTPException(status_code=404, detail="DocType not found")

        update_data = data.model_dump(exclude_unset=True)

        if "metadata_schema" in update_data:
            val = update_data.pop("metadata_schema")
            dt.metadata_schema = json.dumps(val, ensure_ascii=False) if val is not None else None

        for field, value in update_data.items():
            setattr(dt, field, value)

        session.flush()
        return dt.to_dict()


@router.delete("/{doc_type_id}", dependencies=[require_role("editor")])
async def delete_doc_type(doc_type_id: int):
    """Delete a document type (system types cannot be deleted)."""
    with get_dms_session() as session:
        dt = session.query(DocType).filter(DocType.id == doc_type_id).first()
        if not dt:
            raise HTTPException(status_code=404, detail="DocType not found")

        if dt.is_system:
            raise HTTPException(status_code=403, detail="System document types cannot be deleted")

        doc_count = session.query(DmsDocument).filter(DmsDocument.doc_type_id == doc_type_id).count()
        if doc_count > 0:
            raise HTTPException(status_code=409, detail=f"DocType is referenced by {doc_count} document(s)")

        code = dt.code
        session.delete(dt)

        # Also clean up custom keyword rules and folder mapping
        from dms_processor import remove_custom_keyword_rule, remove_folder_mapping
        remove_custom_keyword_rule(code)
        remove_folder_mapping(code)

        return {"success": True, "deleted": code}


# ============================================================
# Keyword Rules & Folder Mapping for DocTypes
# ============================================================

class KeywordRuleRequest(BaseModel):
    keywords: list[str]
    folder_path: Optional[str] = None


@router.get("/config/keyword-rules")
async def list_keyword_rules():
    """Get all keyword→DocType mapping rules (built-in + custom)."""
    from dms_processor import _KEYWORD_DOCTYPE_RULES, get_custom_keyword_rules_list, _BUILTIN_FOLDER_PATHS, _get_custom_folder_mappings

    builtin = [{"keywords": list(kw), "doc_type_code": code, "source": "builtin"} for kw, code in _KEYWORD_DOCTYPE_RULES]
    custom = [{"keywords": r["keywords"], "doc_type_code": r["doc_type_code"], "source": "custom"} for r in get_custom_keyword_rules_list()]

    folder_mappings = {**_BUILTIN_FOLDER_PATHS, **_get_custom_folder_mappings()}

    return {"rules": builtin + custom, "folder_mappings": folder_mappings}


@router.put("/{doc_type_id}/keywords", dependencies=[require_role("editor")])
async def set_keywords(doc_type_id: int, data: KeywordRuleRequest):
    """Set custom keyword rules and optional folder mapping for a DocType."""
    from dms_processor import add_custom_keyword_rule, set_folder_mapping

    with get_dms_session() as session:
        dt = session.query(DocType).filter(DocType.id == doc_type_id).first()
        if not dt:
            raise HTTPException(status_code=404, detail="DocType not found")

        if data.keywords:
            add_custom_keyword_rule(data.keywords, dt.code)

        if data.folder_path:
            set_folder_mapping(dt.code, data.folder_path)

        return {"success": True, "code": dt.code, "keywords": data.keywords, "folder_path": data.folder_path}

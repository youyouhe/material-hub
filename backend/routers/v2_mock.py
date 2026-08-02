"""Mock Document Generation API endpoints."""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_mock")

router = APIRouter(prefix="/api/v2/mock", tags=["mock"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
MOCK_DIR = DATA_DIR / "dms_files" / "mock"


class MockGenerateRequest(BaseModel):
    doc_type_code: str
    entity_name: Optional[str] = None
    person_name: Optional[str] = None
    create_record: bool = True

class MockGenerateOnDemandRequest(BaseModel):
    doc_type_code: str
    entity_name: Optional[str] = None
    person_name: Optional[str] = None
    requirement_context: Optional[dict] = None
    folder_path: Optional[str] = None


@router.post("/generate-on-demand", dependencies=[require_role("editor")])
async def generate_mock_on_demand(body: MockGenerateOnDemandRequest):
    """Generate mock document tailored to a specific tender requirement.

    Key differences from /generate:
    - Sets mock_reason="generated_for_requirement" for downstream tracking
    - Stores requirement_context in meta_json for traceability
    - Idempotent: same (entity, doc_type, tender_project) returns existing
    - Title marked "（MOCK-待替换）"
    """
    from mock_generator import generate_mock, list_mock_types
    from dms_models import get_dms_session, Folder

    valid_types = list_mock_types()
    if body.doc_type_code not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown doc_type_code: {body.doc_type_code}. Valid: {', '.join(valid_types)}",
        )

    # Determine idempotency key from tender project
    idempotency_key = None
    if body.requirement_context:
        idempotency_key = body.requirement_context.get("tender_project")

    try:
        result = generate_mock(
            body.doc_type_code,
            entity_name=body.entity_name,
            person_name=body.person_name,
            create_record=True,
            mock_reason="generated_for_requirement",
            requirement_context=body.requirement_context,
            idempotency_key=idempotency_key,
            folder_path=body.folder_path,
        )
    except Exception as e:
        logger.error(f"Mock on-demand generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "doc_type_code": result["doc_type_code"],
        "doc_type_name": result["doc_type_name"],
        "mock_data": result["mock_data"],
        "image_url": result.get("image_url", ""),
        "document_id": result.get("document_id"),
        "requires_user_replacement": result.get("requires_user_replacement", True),
        "idempotent": result.get("idempotent", False),
    }

@router.get("/types")
async def list_types():
    """List all available mock document type codes."""
    from mock_generator import list_mock_types
    from dms_models import get_dms_session, DocType

    codes = list_mock_types()
    with get_dms_session() as session:
        doc_types = session.query(DocType).filter(DocType.code.in_(codes)).all()
        type_map = {dt.code: dt.name for dt in doc_types}

    result = []
    for code in codes:
        result.append({"code": code, "name": type_map.get(code, code)})

    return {"mock_types": result, "total": len(result)}


@router.post("/generate", dependencies=[require_role("editor")])
async def generate_mock(body: MockGenerateRequest):
    """Generate a mock document with data and PNG image."""
    from mock_generator import generate_mock, list_mock_types

    valid_types = list_mock_types()
    if body.doc_type_code not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown doc_type_code: {body.doc_type_code}. Valid: {', '.join(valid_types)}",
        )

    try:
        result = generate_mock(
            body.doc_type_code,
            entity_name=body.entity_name,
            person_name=body.person_name,
            create_record=body.create_record,
        )
    except Exception as e:
        logger.error(f"Mock generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "doc_type_code": result["doc_type_code"],
        "doc_type_name": result["doc_type_name"],
        "mock_data": result["mock_data"],
        "image_url": result.get("image_url", ""),
        "document_id": result.get("document_id"),
    }


@router.get("/files/{filename}")
async def serve_mock_image(filename: str):
    """Serve a generated mock PNG image."""
    filepath = MOCK_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Mock image not found")
    return FileResponse(str(filepath), media_type="image/png")

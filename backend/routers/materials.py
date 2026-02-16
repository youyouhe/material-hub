"""Material search, browse, and management endpoints."""

import os
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from database import get_session, Material
from models import MaterialUpdate

logger = logging.getLogger("materialhub.routers.materials")

router = APIRouter(prefix="/api", tags=["materials"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
FILES_DIR = DATA_DIR / "files"


@router.get("/materials")
async def search_materials(
    q: Optional[str] = Query(None, description="Search keyword"),
    document_id: Optional[int] = Query(None, description="Filter by document"),
    status: str = Query("valid", description="valid | expired | all"),
):
    """Search and filter materials."""
    with get_session() as session:
        query = session.query(Material)

        # Filter by document
        if document_id is not None:
            query = query.filter(Material.document_id == document_id)

        # Filter by expiry status
        today = date.today()
        if status == "valid":
            query = query.filter(
                (Material.expiry_date.is_(None)) | (Material.expiry_date >= today)
            )
        elif status == "expired":
            query = query.filter(
                Material.expiry_date.isnot(None),
                Material.expiry_date < today,
            )

        materials = query.order_by(Material.document_id, Material.section).all()

        # Keyword search (in-memory for simplicity with SQLite)
        if q:
            keyword = q.lower()
            materials = [
                m
                for m in materials
                if keyword in m.title.lower()
                or keyword in m.section.lower()
                or keyword in (m.image_filename or "").lower()
            ]

        return {"results": [m.to_dict() for m in materials]}


@router.get("/materials/{material_id}")
async def get_material(material_id: int):
    """Get a single material by ID."""
    with get_session() as session:
        mat = session.query(Material).filter(Material.id == material_id).first()
        if not mat:
            raise HTTPException(status_code=404, detail="Material not found")
        return mat.to_dict()


@router.patch("/materials/{material_id}")
async def update_material(material_id: int, update: MaterialUpdate):
    """Update material fields (title, section, expiry_date)."""
    with get_session() as session:
        mat = session.query(Material).filter(Material.id == material_id).first()
        if not mat:
            raise HTTPException(status_code=404, detail="Material not found")

        if update.title is not None:
            mat.title = update.title
        if update.section is not None:
            mat.section = update.section
        if update.expiry_date is not None:
            mat.expiry_date = update.expiry_date

        session.flush()
        return mat.to_dict()


@router.delete("/materials/{material_id}")
async def delete_material(material_id: int):
    """Delete a single material and its image file."""
    with get_session() as session:
        mat = session.query(Material).filter(Material.id == material_id).first()
        if not mat:
            raise HTTPException(status_code=404, detail="Material not found")

        # Delete image file
        try:
            path = Path(mat.image_path)
            if path.exists():
                path.unlink()
        except OSError:
            pass

        # Update parent document counts
        doc = mat.document
        if doc:
            doc.image_count = max(0, doc.image_count - 1)

        session.delete(mat)
        return {"success": True, "deleted": mat.image_filename}


@router.get("/files/{filename:path}")
async def serve_file(filename: str):
    """Serve extracted image files."""
    file_path = FILES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: ensure path doesn't escape FILES_DIR
    try:
        file_path.resolve().relative_to(FILES_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(str(file_path))

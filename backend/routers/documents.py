"""Document upload and extraction endpoints."""

import os
import logging
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from database import get_session, Document, Material
from extractor import extract_materials, _safe_filename

logger = logging.getLogger("materialhub.routers.documents")

router = APIRouter(prefix="/api/documents", tags=["documents"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
FILES_DIR = DATA_DIR / "files"


@router.post("")
async def upload_and_extract(file: UploadFile = File(...)):
    """Upload a .docx file and extract all section images."""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    FILES_DIR.mkdir(parents=True, exist_ok=True)

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Run extraction
        extracted = extract_materials(tmp_path, str(FILES_DIR))

        with get_session() as session:
            # Create document record
            doc = Document(
                filename=file.filename,
                section_count=len({m.section + m.title for m in extracted}),
                image_count=len(extracted),
            )
            session.add(doc)
            session.flush()

            # Create material records
            materials = []
            # Rebuild filenames consistently
            section_counter: dict[str, int] = {}
            for mat in extracted:
                section_key = mat.section or mat.title
                base_name = _safe_filename(
                    f"{mat.section}-{mat.title}" if mat.section else mat.title
                )

                count = section_counter.get(section_key, 0) + 1
                section_counter[section_key] = count

                if count == 1:
                    fname = f"{base_name}.{mat.image_ext}"
                    if not (FILES_DIR / fname).exists():
                        fname = f"{base_name}-01.{mat.image_ext}"
                else:
                    fname = f"{base_name}-{count:02d}.{mat.image_ext}"

                # Find actual file - fallback to pattern match
                if not (FILES_DIR / fname).exists():
                    import glob
                    pattern = str(FILES_DIR / f"{base_name}*")
                    candidates = sorted(glob.glob(pattern))
                    if count <= len(candidates):
                        fname = os.path.basename(candidates[count - 1])

                expiry = None
                if mat.expiry_date:
                    parts = mat.expiry_date.split("-")
                    expiry = date(int(parts[0]), int(parts[1]), int(parts[2]))

                material = Material(
                    document_id=doc.id,
                    section=mat.section,
                    title=mat.title,
                    heading_level=mat.heading_level,
                    image_filename=fname,
                    image_path=str(FILES_DIR / fname),
                    file_size=len(mat.image_data),
                    expiry_date=expiry,
                )
                session.add(material)
                materials.append(material)

            session.flush()

            result = {
                "document_id": doc.id,
                "filename": doc.filename,
                "section_count": doc.section_count,
                "image_count": doc.image_count,
                "materials": [m.to_dict() for m in materials],
            }

        return result

    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")
    finally:
        os.unlink(tmp_path)


@router.get("")
async def list_documents():
    """List all uploaded documents."""
    with get_session() as session:
        docs = session.query(Document).order_by(Document.upload_time.desc()).all()
        return {"documents": [d.to_dict() for d in docs]}


@router.get("/{doc_id}")
async def get_document(doc_id: int):
    """Get document details."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc.to_dict()


@router.delete("/{doc_id}")
async def delete_document(doc_id: int):
    """Delete a document and all its materials."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete image files
        for mat in doc.materials:
            try:
                path = Path(mat.image_path)
                if path.exists():
                    path.unlink()
            except OSError:
                pass

        session.delete(doc)
        return {"success": True, "deleted": doc.filename}

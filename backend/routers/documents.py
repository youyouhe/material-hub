"""Document upload and extraction endpoints."""

import os
import logging
import tempfile
import shutil
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import HTMLResponse
import mammoth
from bs4 import BeautifulSoup

from database import get_session, Document, Material
from extractor import extract_materials, _safe_filename

logger = logging.getLogger("materialhub.routers.documents")

router = APIRouter(prefix="/api/documents", tags=["documents"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
FILES_DIR = DATA_DIR / "files"
DOCS_DIR = DATA_DIR / "docs"


@router.post("")
async def upload_and_extract(
    file: UploadFile = File(...),
    company_id: Optional[int] = Form(None)
):
    """Upload a .docx file and extract all section images."""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    if company_id:
        logger.info(f"📁 上传文档，指定公司ID: {company_id}")

    FILES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Run extraction
        extracted = extract_materials(tmp_path, str(FILES_DIR))

        # Save the original docx file
        safe_docx_name = _safe_filename(file.filename)
        docx_path = DOCS_DIR / f"{safe_docx_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        shutil.copy(tmp_path, docx_path)

        with get_session() as session:
            # Create document record
            doc = Document(
                filename=file.filename,
                docx_path=str(docx_path),
                company_id=company_id,
                section_count=len({m.section + m.title for m in extracted}),
                image_count=len(extracted),
            )
            session.add(doc)
            session.flush()

            # Create material records
            materials = []
            for mat in extracted:
                # Use the actual filename from extractor
                fname = mat.image_filename

                expiry = None
                if mat.expiry_date:
                    parts = mat.expiry_date.split("-")
                    expiry = date(int(parts[0]), int(parts[1]), int(parts[2]))

                material = Material(
                    document_id=doc.id,
                    company_id=company_id,
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

            logger.info(f"Created document {doc.id} with {len(materials)} materials")

            # Save IDs before session closes
            result_doc_id = doc.id
            material_ids = [m.id for m in materials]

            # Explicitly commit before context manager exits
            session.commit()
            logger.info(f"Committed document {result_doc_id} to database")

        # Start auto-processing in background thread (non-blocking)
        def run_auto_processing():
            try:
                from auto_processor import process_materials
                logger.info(f"Starting background auto-processing for document {result_doc_id}")
                process_materials(material_ids, str(FILES_DIR))
                logger.info(f"Background auto-processing completed for document {result_doc_id}")
            except Exception as e:
                logger.error(f"Background auto-processing failed: {e}", exc_info=True)

        # Run in background thread
        thread = threading.Thread(target=run_auto_processing, daemon=True)
        thread.start()
        logger.info(f"Auto-processing started in background thread for document {result_doc_id}")

        # Return immediately without waiting for OCR
        with get_session() as session:
            doc = session.query(Document).filter(Document.id == result_doc_id).first()
            result = {
                "document_id": doc.id,
                "filename": doc.filename,
                "section_count": doc.section_count,
                "image_count": doc.image_count,
                "company_id": doc.company_id,
                "company_name": doc.company.name if doc.company else None,
                "materials": [session.query(Material).get(mid).to_dict() for mid in material_ids],
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


@router.get("/{doc_id}/preview", response_class=HTMLResponse)
async def preview_document(doc_id: int):
    """Get HTML preview of the document."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if not doc.docx_path or not Path(doc.docx_path).exists():
            raise HTTPException(status_code=404, detail="Document file not found")

        try:
            # Convert docx to HTML using mammoth
            with open(doc.docx_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html_content = result.value

            # Get materials for this document to add anchors
            materials = session.query(Material).filter(
                Material.document_id == doc_id
            ).order_by(Material.id).all()

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Strategy: Insert anchors at actual image positions in HTML
            # This provides accurate positioning to where images appear in the document

            # Get all images in the HTML
            html_images = soup.find_all('img')

            logger.info(f"Found {len(html_images)} images in HTML, {len(materials)} materials in DB")

            # Match materials with HTML images by position
            # Assumption: images appear in the same order in HTML as extracted
            for i, mat in enumerate(materials):
                if i < len(html_images):
                    # Insert anchor right before the corresponding image
                    img_tag = html_images[i]
                    anchor = soup.new_tag('span', id=f'section-{mat.id}')
                    anchor['class'] = 'section-anchor'
                    anchor['data-material-id'] = str(mat.id)
                    anchor['data-title'] = f"{mat.section} {mat.title}".strip()
                    img_tag.insert_before(anchor)

                    logger.debug(f"Inserted anchor for material {mat.id} at image position {i}")
                else:
                    # More materials than images in HTML - add anchor at end
                    logger.warning(f"Material {mat.id} has no corresponding HTML image (index {i})")
                    anchor = soup.new_tag('span', id=f'section-{mat.id}')
                    anchor['class'] = 'section-anchor'
                    soup.append(anchor)

            # Build final HTML
            final_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc.filename}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #fff;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            scroll-margin-top: 20px;
        }}
        .section-anchor {{
            display: block;
            position: relative;
            top: -80px;
            visibility: hidden;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
        p {{
            margin: 0.5em 0;
        }}
    </style>
</head>
<body>
{str(soup)}
</body>
</html>
"""

            return HTMLResponse(content=final_html)

        except Exception as e:
            logger.error("Failed to convert document to HTML: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to generate preview: {e}")


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

        # Delete original docx file
        if doc.docx_path:
            try:
                docx_file = Path(doc.docx_path)
                if docx_file.exists():
                    docx_file.unlink()
            except OSError:
                pass

        session.delete(doc)
        return {"success": True, "deleted": doc.filename}

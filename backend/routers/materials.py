"""Material search, browse, and management endpoints."""

import os
import io
import json
import logging
import threading
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from PIL import Image

from database import get_session, Material, Document
from sqlalchemy import func
from models import MaterialUpdate

logger = logging.getLogger("materialhub.routers.materials")

router = APIRouter(prefix="/api", tags=["materials"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
FILES_DIR = DATA_DIR / "files"
IMAGES_DIR = DATA_DIR / "images"

# 确保目录存在
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/materials/upload")
async def upload_single_image(
    image: UploadFile = File(...),
    title: Optional[str] = Form(None),
    section: Optional[str] = Form("手动上传"),
    company_id: Optional[int] = Form(None),
):
    """
    上传单张图片并创建材料

    Args:
        image: 图片文件（PNG/JPG）
        title: 材料标题（可选，默认使用文件名）
        section: 分类（可选，默认"手动上传"）
    """
    try:
        # 验证文件类型
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Only image files are allowed")

        # 读取图片内容
        image_data = await image.read()

        # 验证是否是有效图片
        try:
            img = Image.open(io.BytesIO(image_data))
            img.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image file")

        # 生成文件名（使用哈希避免重复）
        file_hash = hashlib.md5(image_data).hexdigest()[:12]
        original_name = Path(image.filename).stem
        ext = Path(image.filename).suffix.lower()
        if not ext:
            ext = '.png'

        safe_title = title or original_name
        image_filename = f"{safe_title}_{file_hash}{ext}"

        # 保存图片
        image_path = IMAGES_DIR / image_filename
        with open(image_path, 'wb') as f:
            f.write(image_data)

        logger.info(f"📸 手动上传图片: {image_filename} ({len(image_data)} bytes)")

        # 创建Material记录
        with get_session() as session:
            # 创建或获取"手动上传"文档
            manual_doc = session.query(Document).filter(
                Document.filename == "__manual_upload__"
            ).first()

            if not manual_doc:
                manual_doc = Document(
                    filename="__manual_upload__",
                    upload_time=datetime.utcnow(),
                    section_count=0,
                    image_count=0
                )
                session.add(manual_doc)
                session.flush()

            # 创建材料记录
            material = Material(
                document_id=manual_doc.id,
                company_id=company_id,
                section=section or "手动上传",
                title=safe_title,
                heading_level=2,
                image_filename=image_filename,
                image_path=str(image_path),
                file_size=len(image_data),
                created_at=datetime.utcnow()
            )

            session.add(material)
            manual_doc.image_count += 1
            session.flush()

            result = material.to_dict()
            logger.info(f"✅ 材料已创建: ID={material.id}, title={safe_title}")

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 上传图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")


@router.get("/materials")
async def search_materials(
    q: Optional[str] = Query(None, description="Search keyword"),
    document_id: Optional[int] = Query(None, description="Filter by document"),
    status: str = Query("valid", description="valid | expired | all"),
    linked_status: str = Query("all", description="all | company | person | unlinked"),
    source_type: str = Query("all", description="all | docx | manual"),
    company_id: Optional[int] = Query(None, description="Filter by company"),
):
    """Search and filter materials."""
    logger.info(f"🔍 搜索材料: linked_status={linked_status}, source_type={source_type}, status={status}, company_id={company_id}")
    with get_session() as session:
        query = session.query(Material)

        # Filter by document
        if document_id is not None:
            query = query.filter(Material.document_id == document_id)

        # Filter by company
        if company_id is not None:
            query = query.filter(Material.company_id == company_id)
            logger.info(f"  → 过滤: 仅公司ID={company_id}的材料")

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

        # Filter by linked status
        if linked_status == "company":
            query = query.filter(Material.company_id.isnot(None))
            logger.info(f"  → 过滤: 仅关联公司的材料")
        elif linked_status == "person":
            query = query.filter(Material.person_id.isnot(None))
            logger.info(f"  → 过滤: 仅关联人员的材料")
        elif linked_status == "unlinked":
            query = query.filter(
                Material.company_id.is_(None),
                Material.person_id.is_(None)
            )
            logger.info(f"  → 过滤: 仅未关联的材料")

        # Filter by source type
        if source_type == "manual":
            # Manual uploads use the special "__manual_upload__" document
            manual_doc = session.query(Document).filter(
                Document.filename == "__manual_upload__"
            ).first()
            if manual_doc:
                query = query.filter(Material.document_id == manual_doc.id)
            else:
                # No manual uploads exist
                query = query.filter(Material.document_id == -1)  # Return empty
        elif source_type == "docx":
            # Exclude manual uploads
            manual_doc = session.query(Document).filter(
                Document.filename == "__manual_upload__"
            ).first()
            if manual_doc:
                query = query.filter(Material.document_id != manual_doc.id)

        materials = query.order_by(Material.document_id, Material.section).all()
        logger.info(f"  → 查询结果: {len(materials)} 个材料")

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
    """Update material fields (title, section, expiry_date, company_id, person_id)."""
    with get_session() as session:
        mat = session.query(Material).filter(Material.id == material_id).first()
        if not mat:
            raise HTTPException(status_code=404, detail="Material not found")

        # Get only the fields that were explicitly set in the request
        update_data = update.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(mat, field, value)

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


@router.post("/materials/{material_id}/ocr")
async def trigger_ocr(material_id: int):
    """
    触发OCR识别和智能解析（异步处理）

    返回处理状态，实际OCR和LLM解析在后台线程中进行
    """
    with get_session() as session:
        material = session.query(Material).filter(Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")

        # 检查是否已经在处理中
        if material.ocr_status == "processing":
            return {
                "status": "processing",
                "message": "OCR is already processing"
            }

        # 检查图片文件是否存在
        image_path = Path(material.image_path)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")

        # 更新状态为processing
        material.ocr_status = "processing"
        material.ocr_error = None
        session.commit()

        material_id_copy = material_id
        image_path_str = str(image_path)
        title = material.title
        section = material.section

    # 启动后台线程处理
    def process_ocr_background():
        try:
            from ocr_client import ocr_image, check_ocr_service
            from ocr_agent import intelligent_extract, extract_expiry_date, create_entity_from_extraction
            from auto_processor import get_or_create_company, get_or_create_person

            logger.info(f"🔍 开始OCR处理: material_id={material_id_copy}, title={title}")

            # 检查OCR服务
            if not check_ocr_service():
                raise Exception("OCR service not available")

            # Step 1: OCR识别
            logger.info(f"📸 调用OCR服务...")
            ocr_text = ocr_image(image_path_str)
            if not ocr_text:
                raise Exception("OCR recognition failed")

            logger.info(f"✅ OCR成功，文本长度: {len(ocr_text)} chars")

            # Step 2: LLM智能解析
            logger.info(f"🤖 LLM智能解析中...")
            extraction_result = intelligent_extract(ocr_text, title)

            material_type = extraction_result.get("material_type", "unknown")
            extracted_data = extraction_result.get("extracted_data", {})
            confidence = extraction_result.get("confidence", 0.0)

            logger.info(f"✅ 解析完成: type={material_type}, confidence={confidence:.2f}")

            # Step 3: 提取有效期
            expiry_date = extract_expiry_date(extracted_data)

            # Step 4: 创建实体（公司或人员）
            entity_info = create_entity_from_extraction(material_type, extracted_data)
            company_id = None
            person_id = None

            if entity_info["entity_type"] == "company":
                company_id = get_or_create_company(entity_info["entity_data"])
                logger.info(f"✅ 公司实体: ID={company_id}")

            elif entity_info["entity_type"] == "person":
                person_id = get_or_create_person(entity_info["entity_data"], company_id)
                logger.info(f"✅ 人员实体: ID={person_id}")

            # Step 5: 保存结果到数据库
            with get_session() as session:
                mat = session.query(Material).filter(Material.id == material_id_copy).first()
                if mat:
                    mat.ocr_text = ocr_text
                    mat.material_type = material_type
                    mat.extracted_json = json.dumps(extraction_result, ensure_ascii=False)
                    mat.ocr_status = "completed"
                    mat.ocr_processed_at = datetime.utcnow()

                    if expiry_date:
                        # 转换字符串日期为date对象
                        try:
                            year, month, day = expiry_date.split('-')
                            mat.expiry_date = date(int(year), int(month), int(day))
                            logger.info(f"✅ 有效期: {expiry_date}")
                        except (ValueError, AttributeError) as e:
                            logger.warning(f"⚠ 有效期格式错误: {expiry_date}, {e}")

                    if company_id:
                        mat.company_id = company_id

                    if person_id:
                        mat.person_id = person_id

                    session.commit()
                    logger.info(f"✅ OCR处理完成: material_id={material_id_copy}")

        except Exception as e:
            logger.error(f"❌ OCR处理失败: {e}", exc_info=True)
            with get_session() as session:
                mat = session.query(Material).filter(Material.id == material_id_copy).first()
                if mat:
                    mat.ocr_status = "failed"
                    mat.ocr_error = str(e)
                    mat.ocr_processed_at = datetime.utcnow()
                    session.commit()

    # 启动后台线程
    thread = threading.Thread(target=process_ocr_background, daemon=True)
    thread.start()

    return {
        "status": "processing",
        "message": "OCR processing started in background",
        "material_id": material_id
    }


@router.get("/materials/{material_id}/ocr")
async def get_ocr_result(material_id: int):
    """
    获取OCR识别结果和提取的结构化数据

    Returns:
        {
            "status": "pending|processing|completed|failed",
            "ocr_text": "...",  // OCR原始文本，未处理则为null
            "extracted_data": {...},  // 提取的结构化数据，未处理则为null
            "material_type": "...",
            "error": "...",  // 如果失败，包含错误信息
            "processed_at": "..."
        }
    """
    with get_session() as session:
        material = session.query(Material).filter(Material.id == material_id).first()
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")

        # 解析extracted_json
        extracted_data = None
        if material.extracted_json:
            try:
                extracted_data = json.loads(material.extracted_json)
            except:
                pass

        return {
            "status": material.ocr_status or "pending",
            "ocr_text": material.ocr_text,
            "extracted_data": extracted_data,
            "material_type": material.material_type,
            "error": material.ocr_error,
            "processed_at": material.ocr_processed_at.isoformat() if material.ocr_processed_at else None
        }

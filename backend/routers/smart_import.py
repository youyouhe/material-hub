"""
智能导入API路由
"""

import os
import logging
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks, Body
from fastapi.responses import FileResponse, Response

from database import get_session, PendingReview
from smart_import import SmartImportPipeline

logger = logging.getLogger("materialhub.routers.smart_import")

router = APIRouter(prefix="/api/smart-import", tags=["smart-import"])


@router.post("/single")
async def single_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Query("auto", description="导入模式: auto(自动分析) 或 manual(手动选页)")
):
    """
    单文件智能导入

    参数:
    - mode: auto(默认，自动分析) 或 manual(手动选页，仅PDF)

    auto模式: 立即返回pending_id，后台异步处理文件并更新进度
    manual模式: 保存文件并返回PDF页数，等待用户选择页面后调用reanalyze接口
    """
    import json
    import tempfile
    import shutil
    from pathlib import Path
    import io

    # 先保存临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name

    # 手动选页模式：仅保存文件，返回页数，不启动处理
    if mode == "manual" and file.filename.lower().endswith('.pdf'):
        import fitz
        try:
            doc = fitz.open(temp_path)
            total_pages = len(doc)
            doc.close()
        except Exception as e:
            os.unlink(temp_path)
            raise HTTPException(status_code=400, detail=f"无法读取PDF文件: {e}")

        with get_session() as session:
            pending_item = PendingReview(
                filename=file.filename,
                file_path=temp_path,
                file_type="document",
                status="awaiting_selection",
                processing_progress=json.dumps({
                    "stage": "awaiting_selection",
                    "message": "等待用户选择页面",
                    "total_pages": total_pages
                }, ensure_ascii=False)
            )
            session.add(pending_item)
            session.commit()
            pending_id = pending_item.id

        logger.info(f"📄 手动选页模式: {file.filename}, 共{total_pages}页, pending_id={pending_id}")

        return {
            "status": "awaiting_selection",
            "pending_id": pending_id,
            "total_pages": total_pages,
            "filename": file.filename,
            "message": f"文件已上传（共{total_pages}页），请选择要分析的页面"
        }

    # auto模式 + PDF: 保存文件，返回预览确认状态（用户可旋转后再提交）
    if mode == "auto" and file.filename.lower().endswith('.pdf'):
        import fitz
        try:
            doc = fitz.open(temp_path)
            total_pages = len(doc)
            doc.close()
        except Exception as e:
            os.unlink(temp_path)
            raise HTTPException(status_code=400, detail=f"无法读取PDF文件: {e}")

        with get_session() as session:
            pending_item = PendingReview(
                filename=file.filename,
                file_path=temp_path,
                file_type="document",
                status="awaiting_confirmation",
                processing_progress=json.dumps({
                    "stage": "awaiting_confirmation",
                    "message": "等待用户确认后开始分析",
                    "total_pages": total_pages
                }, ensure_ascii=False)
            )
            session.add(pending_item)
            session.commit()
            pending_id = pending_item.id

        logger.info(f"📄 自动模式PDF预览: {file.filename}, 共{total_pages}页, pending_id={pending_id}")

        return {
            "status": "awaiting_confirmation",
            "pending_id": pending_id,
            "total_pages": total_pages,
            "filename": file.filename,
            "message": f"文件已上传（共{total_pages}页），请预览确认后开始分析"
        }

    # 非PDF文件（图片等）：直接后台处理
    # 创建待审核记录（状态为processing）
    with get_session() as session:
        pending_item = PendingReview(
            filename=file.filename,
            file_path=temp_path,
            file_type="document" if file.filename.lower().endswith('.pdf') else "image",
            status="processing",
            processing_progress=json.dumps({
                "stage": "preparing",
                "message": "准备处理...",
                "current_page": 0,
                "total_pages": 0,
                "ocr_results": []
            }, ensure_ascii=False)
        )
        session.add(pending_item)
        session.commit()
        pending_id = pending_item.id

    logger.info(f"📝 创建待审核记录 ID={pending_id}: {file.filename}")

    # 同步处理函数（在后台任务中运行）
    def process_file_sync():
        import asyncio
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 读取文件内容
            with open(temp_path, 'rb') as f:
                file_content = f.read()

            # 创建模拟的UploadFile对象
            mock_file = UploadFile(
                filename=file.filename,
                file=io.BytesIO(file_content)
            )

            pipeline = SmartImportPipeline()

            # 传递pending_id，让处理过程能更新进度
            result = loop.run_until_complete(pipeline.process_single_file(mock_file, pending_id=pending_id))
            logger.info(f"✅ 单文件导入完成: {result}")

            loop.close()

        except Exception as e:
            logger.error(f"单文件导入失败: {e}", exc_info=True)

            # 更新状态为失败
            with get_session() as session:
                item = session.query(PendingReview).get(pending_id)
                if item:
                    item.status = "pending"
                    item.processing_progress = json.dumps({
                        "stage": "error",
                        "message": f"处理失败: {str(e)}"
                    }, ensure_ascii=False)
                    session.commit()

    # 启动后台任务
    background_tasks.add_task(process_file_sync)

    # 立即返回pending_id，让前端开始轮询
    return {
        "status": "processing",
        "pending_id": pending_id,
        "filename": file.filename,
        "message": "文件已接收，正在后台处理..."
    }


@router.post("/batch")
async def batch_import(files: List[UploadFile] = File(...)):
    """
    批量智能导入文件

    支持的格式：
    - 图片: jpg, jpeg, png, bmp, tiff, gif
    - 文档: pdf, docx, doc

    返回：
    {
        "total": 总数,
        "auto_archived": 自动归档数,
        "pending_review": 待审核数,
        "failed": 失败数,
        "items": [详细结果列表]
    }
    """
    logger.info(f"📦 开始批量导入，共 {len(files)} 个文件")

    pipeline = SmartImportPipeline()

    results = {
        "total": len(files),
        "auto_archived": 0,
        "pending_review": 0,
        "failed": 0,
        "items": []
    }

    for file in files:
        try:
            result = await pipeline.process_single_file(file)
            results["items"].append(result)

            if result["status"] == "auto_archived":
                results["auto_archived"] += 1
            elif result["status"] == "pending_review":
                results["pending_review"] += 1
            else:
                results["failed"] += 1

        except Exception as e:
            logger.error(f"处理文件失败: {file.filename} - {e}")
            results["failed"] += 1
            results["items"].append({
                "status": "failed",
                "filename": file.filename,
                "error": str(e)
            })

    logger.info(f"✅ 批量导入完成: 成功={results['auto_archived']}, 待审核={results['pending_review']}, 失败={results['failed']}")

    return results


@router.get("/pending-reviews")
async def get_pending_reviews(
    status: str = Query("pending", description="状态: pending/approved/rejected"),
    limit: int = Query(50, le=100, description="返回数量限制")
):
    """
    获取待审核列表
    """
    with get_session() as session:
        query = session.query(PendingReview).filter(
            PendingReview.status == status
        ).order_by(
            PendingReview.created_at.desc()
        )

        items = query.limit(limit).all()
        total = query.count()

        return {
            "total": total,
            "items": [item.to_dict() for item in items]
        }


@router.get("/pending-reviews/{id}")
async def get_pending_review(id: int):
    """
    获取单个待审核项详情
    """
    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        return item.to_dict()


@router.get("/pending-reviews/{id}/preview")
async def get_pending_review_preview(id: int):
    """
    获取待审核项的文件预览
    支持通过URL参数传递token: ?token=xxx
    (认证由中间件处理)
    """
    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        file_path = Path(item.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 根据文件扩展名确定正确的media_type
        import mimetypes
        from urllib.parse import quote

        media_type, _ = mimetypes.guess_type(str(file_path))
        if not media_type:
            if item.file_type == "image":
                media_type = "image/jpeg"
            else:
                media_type = "application/pdf"

        # 使用RFC 2231编码中文文件名，并使用inline让浏览器预览而不是下载
        filename_encoded = quote(item.filename)
        return FileResponse(
            path=file_path,
            media_type=media_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{filename_encoded}"
            }
        )


@router.get("/pending-reviews/{id}/thumbnails/{page_num}")
async def get_page_thumbnail(id: int, page_num: int):
    """
    获取PDF指定页面的缩略图（JPEG）
    page_num: 从1开始的页码
    用于手动选页模式的页面预览
    使用磁盘缓存加速重复访问
    """
    import fitz
    import hashlib

    with get_session() as session:
        item = session.query(PendingReview).get(id)
        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")
        file_path = item.file_path

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_path.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="仅支持PDF文件")

    try:
        # 创建缩略图缓存目录
        cache_dir = Path("data/thumbnail_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 使用文件路径+修改时间+页码作为缓存key（文件变化后缓存失效）
        file_stat = os.stat(file_path)
        file_mtime = str(file_stat.st_mtime)
        cache_key = hashlib.md5(f"{file_path}_{file_mtime}_{page_num}".encode()).hexdigest()
        cache_file = cache_dir / f"{cache_key}.jpg"

        # 检查缓存
        if cache_file.exists():
            # 从缓存读取
            img_bytes = cache_file.read_bytes()
        else:
            # 生成缩略图
            doc = fitz.open(file_path)
            total = len(doc)

            if page_num < 1 or page_num > total:
                doc.close()
                raise HTTPException(status_code=400, detail=f"页码无效，PDF共{total}页")

            page = doc[page_num - 1]
            # 96 DPI 缩略图（默认PDF 72 DPI，缩放1.33x，足够预览）
            mat = fitz.Matrix(96 / 72, 96 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            # 写入缓存
            cache_file.write_bytes(img_bytes)

        return Response(
            content=img_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": f"inline; filename=page_{page_num}.jpg"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成缩略图失败: {e}")


@router.post("/pending-reviews/{id}/rotate")
async def rotate_pending_pdf(id: int, direction: str = Query("left", description="旋转方向: left(逆时针90°) 或 right(顺时针90°)")):
    """
    旋转待审核PDF的所有页面
    direction: left(逆时针90°) 或 right(顺时针90°)
    """
    import fitz

    if direction not in ("left", "right"):
        raise HTTPException(status_code=400, detail="direction 必须是 left 或 right")

    with get_session() as session:
        item = session.query(PendingReview).get(id)
        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")
        file_path = item.file_path

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_path.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="仅支持PDF文件")

    try:
        rotation = -90 if direction == "left" else 90
        doc = fitz.open(file_path)
        for page in doc:
            page.set_rotation((page.rotation + rotation) % 360)
        doc.save(file_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        total_pages = len(doc)
        doc.close()

        logger.info(f"🔄 旋转PDF: pending_id={id}, direction={direction}, pages={total_pages}")

        return {
            "status": "success",
            "total_pages": total_pages,
            "direction": direction,
            "message": f"已向{'左' if direction == 'left' else '右'}旋转90°"
        }
    except Exception as e:
        logger.error(f"旋转PDF失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"旋转失败: {e}")


@router.post("/pending-reviews/{id}/approve")
async def approve_pending_review(id: int, corrections: Optional[dict] = None):
    """
    批准待审核项（可选修正信息）

    corrections 示例:
    {
        "company_id": 123,
        "material_type": "license",
        "expiry_date": "2026-12-31"
    }
    """
    import json
    from smart_import import AutoArchiver

    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        if item.status != "pending":
            raise HTTPException(status_code=400, detail="该项已经被审核过")

        # 解析存储的数据
        analysis = json.loads(item.analysis_json)
        entities = json.loads(item.entities_json)
        file_info = {"type": item.file_type, "extension": Path(item.filename).suffix}

        # 应用用户修正
        extract_all_pages = False
        if corrections:
            if "company_id" in corrections:
                entities["company_id"] = corrections["company_id"]
            if "material_type" in corrections:
                analysis["material_type"] = corrections["material_type"]
            if "material_name" in corrections:
                analysis["material_name"] = corrections["material_name"]
            if "expiry_date" in corrections:
                if not analysis.get("key_dates"):
                    analysis["key_dates"] = {}
                analysis["key_dates"]["expiry_date"] = corrections["expiry_date"]
            # 提取所有页面为PNG选项
            if "extract_all_pages" in corrections:
                extract_all_pages = corrections["extract_all_pages"]

        # 执行归档
        archiver = AutoArchiver()
        material = await archiver.archive(
            temp_path=item.file_path,
            filename=item.filename,
            file_info=file_info,
            analysis=analysis,
            entities=entities,
            extract_all_pages=extract_all_pages
        )

        # 更新审核状态
        item.status = "approved"
        item.reviewed_at = __import__('datetime').datetime.utcnow()
        session.commit()

        return {
            "status": "success",
            "message": "已批准并归档",
            "material_id": material["id"],
            "pending_id": id
        }


@router.post("/pending-reviews/{id}/reject")
async def reject_pending_review(id: int, reason: str = ""):
    """
    拒绝待审核项
    """
    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        if item.status != "pending":
            raise HTTPException(status_code=400, detail="该项已经被审核过")

        # 更新审核状态
        item.status = "rejected"
        item.reviewed_at = __import__('datetime').datetime.utcnow()
        item.review_notes = reason
        session.commit()

        # 删除临时文件
        file_path = Path(item.file_path)
        if file_path.exists():
            file_path.unlink()

        return {
            "status": "success",
            "message": "已拒绝",
            "pending_id": id
        }


@router.post("/pending-reviews/{id}/reanalyze")
async def reanalyze_pending_review(
    id: int,
    background_tasks: BackgroundTasks,
    page_numbers: Optional[List[int]] = Body(None, embed=True),
    extract_all_pages: bool = Body(False, embed=True)
):
    """
    重新分析待审核项（后台异步处理，立即返回）

    参数:
    - page_numbers: 可选，指定要扫描的页码列表（从1开始），例如：[1, 3, 5]
                   如果不提供，默认扫描前5页
    - extract_all_pages: 可选，是否提取所有页面为PNG（默认false）

    请求体示例:
    {
        "page_numbers": [1, 3, 5],
        "extract_all_pages": true
    }
    或者不传递 page_numbers（使用默认模式）
    """
    import json

    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        # 保存文件路径和文件名
        temp_file_path = item.file_path
        original_filename = item.filename

        # 检查临时文件是否存在
        if not os.path.exists(temp_file_path):
            raise HTTPException(status_code=404, detail="临时文件不存在")

        # 记录原始状态（用于失败时回退）
        original_status = item.status

        # 标记为处理中状态
        item.status = "processing"
        item.processing_progress = json.dumps({
            "stage": "preparing",
            "message": "准备重新分析...",
            "current_page": 0,
            "total_pages": 0,
            "ocr_results": []
        }, ensure_ascii=False)
        session.commit()

        processing_id = item.id

    # 失败时回退的状态
    fallback_status = original_status if original_status in ("awaiting_selection", "awaiting_confirmation") else "awaiting_selection"

    if page_numbers:
        logger.info(f"🔄 重新分析: {original_filename}，指定页码: {page_numbers}")
    else:
        logger.info(f"🔄 重新分析: {original_filename}")

    # 后台同步处理函数（在独立线程中运行，不阻塞事件循环）
    def process_reanalyze_sync():
        import asyncio
        import io
        from fastapi import UploadFile

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 读取临时文件内容
            with open(temp_file_path, 'rb') as f:
                file_content = f.read()

            mock_file = UploadFile(
                filename=original_filename,
                file=io.BytesIO(file_content)
            )

            pipeline = SmartImportPipeline()
            result = loop.run_until_complete(pipeline.process_single_file(
                mock_file,
                pending_id=processing_id,
                page_numbers=page_numbers,
                extract_all_pages=extract_all_pages
            ))
            logger.info(f"✅ 重新分析完成: {result}")

            # process_single_file 内部已经正确更新了 PendingReview 状态
            # 只需处理 pending_id 不匹配的情况（创建了新记录需要合并回原记录）
            with get_session() as session:
                if result.get('status') == 'pending_review' and result.get('pending_id') != processing_id:
                    item = session.query(PendingReview).get(processing_id)
                    new_item = session.query(PendingReview).get(result['pending_id'])
                    if item and new_item:
                        item.analysis_json = new_item.analysis_json
                        item.entities_json = new_item.entities_json
                        item.confidence = new_item.confidence
                        item.status = "pending"
                        item.processing_progress = None
                        session.delete(new_item)
                        session.commit()

            loop.close()

        except Exception as e:
            logger.error(f"重新分析失败: {e}", exc_info=True)

            with get_session() as session:
                item = session.query(PendingReview).get(processing_id)
                if item:
                    if item.analysis_json:
                        item.status = "pending"
                    else:
                        # 回退到之前的等待状态（手动选页 or 自动预览）
                        item.status = fallback_status
                    item.processing_progress = json.dumps({
                        "stage": "error",
                        "message": f"分析失败: {str(e)}"
                    }, ensure_ascii=False)
                    session.commit()

    # 启动后台任务（独立线程），立即返回
    background_tasks.add_task(process_reanalyze_sync)

    return {
        "status": "processing",
        "pending_id": processing_id,
        "filename": original_filename,
        "message": "已开始重新分析，请通过进度接口查询"
    }


@router.get("/pending-reviews/{id}/progress")
async def get_pending_review_progress(id: int):
    """
    获取待审核项的处理进度
    """
    import json

    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        if item.status != "processing":
            return {
                "status": item.status,
                "progress": None
            }

        progress_data = {}
        if item.processing_progress:
            try:
                progress_data = json.loads(item.processing_progress)
            except:
                pass

        return {
            "status": "processing",
            "progress": progress_data
        }


@router.delete("/pending-reviews/{id}")
async def delete_pending_review(id: int):
    """
    删除待审核项（清理临时文件）
    """
    with get_session() as session:
        item = session.query(PendingReview).get(id)

        if not item:
            raise HTTPException(status_code=404, detail="待审核项不存在")

        # 删除临时文件
        file_path = Path(item.file_path)
        if file_path.exists():
            file_path.unlink()

        # 删除数据库记录
        session.delete(item)
        session.commit()

        return {"status": "success", "message": "已删除"}


@router.get("/stats")
async def get_import_stats():
    """
    获取导入统计信息
    """
    with get_session() as session:
        pending_count = session.query(PendingReview).filter(
            PendingReview.status == "pending"
        ).count()

        approved_count = session.query(PendingReview).filter(
            PendingReview.status == "approved"
        ).count()

        rejected_count = session.query(PendingReview).filter(
            PendingReview.status == "rejected"
        ).count()

        return {
            "pending": pending_count,
            "approved": approved_count,
            "rejected": rejected_count,
            "total": pending_count + approved_count + rejected_count
        }

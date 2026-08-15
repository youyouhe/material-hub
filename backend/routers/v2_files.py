"""DMS File Storage API endpoints."""

import os
import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse

from dms_models import get_dms_session, DmsFile, Revision, DmsDocument
from dms_auth import require_role, get_current_user_id
from dms_audit import log_audit

logger = logging.getLogger("materialhub.routers.v2_files")

router = APIRouter(prefix="/api/v2", tags=["dms-files"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DMS_FILES_DIR = DATA_DIR / "dms_files"
DMS_FILES_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "audio/mpeg", "audio/mp3", "audio/mpga", "audio/mpa",
    "audio/wav", "audio/wave", "audio/x-wav",
    "audio/ogg", "audio/flac", "audio/aac",
    "audio/webm", "audio/mp4", "audio/x-m4a",
    "application/octet-stream",
    "video/mp4", "video/mpeg", "video/quicktime",
    "video/webm", "video/x-msvideo", "video/x-matroska",
    "text/plain",
}
SAFE_INLINE_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# 预览降采样:超大图片(如上亿像素的扫描件)直接返回原图会超出浏览器解码上限,
# 表现为一直加载/只渲染一条。预览时降到长边 2048 的 JPEG,按文件哈希缓存。
PREVIEW_MAX_DIM = 2048
PREVIEW_CACHE_DIR = DMS_FILES_DIR / "_preview_cache"


def _get_preview_rendition(file_id: int, file_path: Path, file_hash: str) -> Path:
    """返回用于预览的图片路径。超大图生成(或复用)降采样缓存,否则返回原图。"""
    try:
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS = 500_000_000  # 入库文件可信,放宽到 5 亿像素
        with Image.open(file_path) as im:
            w, h = im.size
        if max(w, h) <= PREVIEW_MAX_DIM:
            return file_path

        PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = PREVIEW_CACHE_DIR / f"{file_id}_{(file_hash or 'nohash')[:16]}.jpg"
        if not cache_path.exists():
            with Image.open(file_path) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((PREVIEW_MAX_DIM, PREVIEW_MAX_DIM))
                im.convert("RGB").save(cache_path, "JPEG", quality=85)
            logger.info(f"Preview rendition generated for file {file_id}: {w}x{h} -> {im.size}")
        return cache_path
    except Exception as e:
        logger.warning(f"Preview downscale failed for file {file_id}, serving original: {e}")
        return file_path


def _sanitize_upload_filename(raw: str) -> str:
    """Strip path components, null bytes, and traversal segments from an uploaded filename."""
    name = os.path.basename(raw or "")
    name = name.replace("\x00", "")
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="无效的文件名")
    return name


@router.post("/documents/{doc_id}/revisions/{rev_id}/files/", dependencies=[require_role("editor")])
async def upload_file(
    doc_id: int,
    rev_id: int,
    file: UploadFile = File(...),
    file_type: str = Form("original"),
    page_number: int = Form(None),
):
    """Upload a file to a specific revision."""
    with get_dms_session() as session:
        rev = session.query(Revision).filter(
            Revision.id == rev_id,
            Revision.document_id == doc_id,
        ).first()
        if not rev:
            raise HTTPException(status_code=404, detail="Revision not found")

        # Read file content
        content = await file.read()
        # Validate MIME type to prevent stored XSS (e.g. text/html served inline)
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail="不支持的文件类型")
        file_hash = hashlib.md5(content).hexdigest()
        file_size = len(content)

        # Check for duplicate in same revision
        existing = session.query(DmsFile).filter(
            DmsFile.revision_id == rev_id,
            DmsFile.file_hash == file_hash,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Duplicate file in this revision")

        # Build storage path: dms_files/{doc_id}/{rev_id}/{filename}
        rev_dir = DMS_FILES_DIR / str(doc_id) / str(rev_id)
        rev_dir.mkdir(parents=True, exist_ok=True)

        # Add hash prefix to avoid name collisions
        safe_name = f"{file_hash[:8]}_{_sanitize_upload_filename(file.filename)}"
        storage_path = f"dms_files/{doc_id}/{rev_id}/{safe_name}"
        full_path = DATA_DIR / storage_path
        # Path traversal protection: resolved path must stay inside DATA_DIR
        if not str(full_path.resolve()).startswith(str(DATA_DIR.resolve())):
            raise HTTPException(status_code=403, detail="非法路径")

        with open(full_path, "wb") as f:
            f.write(content)

        # Create file record
        dms_file = DmsFile(
            revision_id=rev_id,
            file_type=file_type,
            filename=file.filename,
            storage_path=storage_path,
            mime_type=file.content_type,
            file_size=file_size,
            file_hash=file_hash,
            page_number=page_number,
        )
        session.add(dms_file)
        session.flush()

        logger.info(f"File uploaded: {file.filename} -> {storage_path} ({file_size} bytes)")
        return dms_file.to_dict()


ROTATABLE_MIME_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/webp"}


@router.post("/files/{file_id}/rotate", dependencies=[require_role("editor")])
async def rotate_file(file_id: int, request: Request, angle: int = Query(90)):
    """顺时针旋转图片文件（就地修改）。用于修正倒立/横躺的扫描件，便于查看和重新 OCR。"""
    if angle not in (90, 180, 270):
        raise HTTPException(status_code=400, detail="angle 只支持 90/180/270")

    with get_dms_session() as session:
        dms_file = session.query(DmsFile).filter(DmsFile.id == file_id).first()
        if not dms_file:
            raise HTTPException(status_code=404, detail="File not found")
        if dms_file.mime_type not in ROTATABLE_MIME_TYPES:
            raise HTTPException(status_code=400, detail="仅支持图片文件旋转")

        file_path = DATA_DIR / dms_file.storage_path
        # Path traversal protection
        try:
            file_path.resolve().relative_to(DATA_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Physical file not found on disk")

        try:
            from PIL import Image, ImageOps
            with Image.open(file_path) as img:
                fmt = (img.format or "PNG").upper()
                if fmt == "JPG":
                    fmt = "JPEG"
                # 先按 EXIF 方向归一化，避免旋转后查看器按 EXIF 二次旋转
                img = ImageOps.exif_transpose(img)
                rotated = img.rotate(-angle, expand=True)
                if fmt == "JPEG" and rotated.mode not in ("RGB", "L"):
                    rotated = rotated.convert("RGB")
                rotated.save(file_path, format=fmt)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rotate failed for file {file_id}: {e}")
            raise HTTPException(status_code=500, detail=f"旋转失败: {e}")

        # 旋转改变了文件内容，更新大小与哈希
        content = file_path.read_bytes()
        dms_file.file_size = len(content)
        dms_file.file_hash = hashlib.md5(content).hexdigest()

        uid = getattr(request.state, "user_id", None)
        rev = session.query(Revision).filter(Revision.id == dms_file.revision_id).first()
        if rev and uid:
            doc = session.query(DmsDocument).filter(DmsDocument.id == rev.document_id).first()
            if doc:
                log_audit(session, uid, "rotate", "document", doc.id, doc.title,
                          details={"file_id": file_id, "filename": dms_file.filename, "angle": angle},
                          ip_address=request.client.host if request.client else None)

        logger.info(f"File {file_id} rotated {angle}° clockwise: {dms_file.filename}")
        return dms_file.to_dict()


@router.get("/files/{file_id}")
async def serve_file(file_id: int, request: Request, preview: bool = Query(False)):
    """Serve a file by its database ID."""
    with get_dms_session() as session:
        dms_file = session.query(DmsFile).filter(DmsFile.id == file_id).first()
        if not dms_file:
            raise HTTPException(status_code=404, detail="File not found")

        file_path = DATA_DIR / dms_file.storage_path

        # Path traversal protection
        try:
            file_path.resolve().relative_to(DATA_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Physical file not found on disk")

        # Audit log for original file downloads (skip thumbnails/extracted pages)
        if dms_file.file_type == "original":
            uid = getattr(request.state, "user_id", None)
            # Find parent document via revision
            rev = session.query(Revision).filter(Revision.id == dms_file.revision_id).first()
            if rev and uid:
                doc = session.query(DmsDocument).filter(DmsDocument.id == rev.document_id).first()
                if doc:
                    log_audit(session, uid, "download", "document", doc.id, doc.title,
                              details={"file_id": file_id, "filename": dms_file.filename},
                              ip_address=request.client.host if request.client else None)

        # Determine a safe download filename (basename only, no null bytes / quotes)
        safe_name = os.path.basename(dms_file.filename or "") or "file"
        safe_name = safe_name.replace("\x00", "").replace('"', "")

        if preview and dms_file.mime_type in SAFE_INLINE_MIME:
            # Inline display only for known-safe image MIME types
            serve_path = _get_preview_rendition(file_id, file_path, dms_file.file_hash)
            media_type = "image/jpeg" if serve_path != file_path else dms_file.mime_type
            resp = FileResponse(
                str(serve_path),
                media_type=media_type,
            )
            resp.headers["Content-Disposition"] = "inline"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            # 文件可能被旋转等操作就地修改，禁用启发式缓存，强制每次回源校验
            resp.headers["Cache-Control"] = "no-cache"
            return resp

        # Non-image preview, or default download: force download, never render in-browser
        resp = FileResponse(
            str(file_path),
            media_type="application/octet-stream",
        )
        from urllib.parse import quote
        # Starlette requires latin-1 encodable header values. Use ASCII fallback
        # for filename= and RFC 5987 filename* for the real (non-ASCII) name.
        ascii_name = safe_name.encode("ascii", "ignore").decode("ascii") or "file"
        resp.headers["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(safe_name)}"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

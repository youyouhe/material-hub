"""
DMS Document Processing Pipeline.

Background processor that runs OCR, LLM analysis, auto-classification,
entity linking, page extraction, and thumbnail generation on uploaded documents.

Reuses existing modules (read-only):
- ocr_client.py — OCR service HTTP client
- ocr_agent.py — LLM-based document analysis
- ocr_cache.py — OCR result caching by file hash
- page_extraction_strategy.py — Smart page selection for PDFs
"""

import gc
import json
import logging
import os
import tempfile
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("materialhub.dms_processor")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DMS_FILES_DIR = DATA_DIR / "dms_files"

# --- Mapping dicts (same as migrate_to_dms.py) ---

# Legacy code-based mapping (kept for backward compat with old data)
_LEGACY_TYPE_TO_DOCTYPE = {
    "license": "business-license",
    "legal_person_cert": "business-license",
    "qualification": "qualification-cert",
    "iso_cert": "iso-cert",
    "honor": "honor-award",
    "id_card": "id-card",
    "education": "education-cert",
    "certificate": "professional-cert",
    "professional_cert": "professional-cert",
    "contract": "contract",
    "acceptance": "acceptance-report",
    "bid": "bid-document",
    "authorization": "authorization",
    "invoice": "invoice",
    "product_brochure": "product-brochure",
    "company_profile": "company-profile",
    "technical_doc": "technical-doc",
}

# Keyword → DocType code mapping for free-form Chinese material_type from LLM
# Order matters: more specific keywords should come first
_KEYWORD_DOCTYPE_RULES = [
    # 营业执照
    (["营业执照"], "business-license"),
    (["法定代表人", "法人证明"], "business-license"),
    # 资质证书
    (["资质证书", "资质等级", "安全生产许可", "施工许可", "增值电信"], "qualification-cert"),
    # ISO认证
    (["iso", "ISO", "体系认证", "质量管理体系", "环境管理体系", "信息安全"], "iso-cert"),
    # 荣誉奖项
    (["荣誉", "奖项", "奖状", "表彰", "专利证书", "软件著作权"], "honor-award"),
    # 身份证
    (["身份证", "居民身份"], "id-card"),
    # 学历证书
    (["毕业证", "学历证", "学位证", "毕业", "学历", "学位"], "education-cert"),
    # 职称证书
    (["职称", "职业资格", "执业资格", "建造师", "工程师", "会计师", "注册师"], "professional-cert"),
    # 合同
    (["合同", "协议书", "委托合同", "采购合同", "服务合同"], "contract"),
    # 验收报告
    (["验收报告", "验收", "竣工报告"], "acceptance-report"),
    # 投标文件
    (["投标", "招标", "中标通知", "磋商", "响应文件"], "bid-document"),
    # 授权文件
    (["授权书", "委托书", "授权", "代理证明"], "authorization"),
    # 发票
    (["发票", "收据", "增值税"], "invoice"),
    # 产品资料
    (["产品说明", "产品手册", "产品介绍", "产品彩页", "技术参数", "产品目录"], "product-brochure"),
    # 公司简介
    (["公司简介", "企业简介", "公司介绍", "企业宣传", "公司概况"], "company-profile"),
    # 技术文档
    (["技术方案", "实施方案", "技术文档", "设计方案", "解决方案"], "technical-doc"),
]


def _get_learned_mappings() -> dict:
    """Load user-confirmed type mappings from settings."""
    try:
        from dms_models import get_setting
        import json
        raw = get_setting("type_mapping_learned")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


def _save_learned_mappings(mappings: dict):
    """Persist learned type mappings to settings."""
    try:
        from dms_models import set_setting
        import json
        set_setting("type_mapping_learned", json.dumps(mappings, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"Failed to save learned type mappings: {e}")


def learn_type_mapping(material_type_text: str, doc_type_code: str):
    """Learn a new mapping from user confirmation.
    Called when user manually selects a DocType for a material_type that wasn't auto-matched.
    """
    if not material_type_text or not doc_type_code:
        return
    text = material_type_text.strip()
    if not text:
        return

    # Skip if already matched by built-in rules
    if match_material_type(text) == doc_type_code:
        return

    mappings = _get_learned_mappings()
    mappings[text] = doc_type_code
    _save_learned_mappings(mappings)
    logger.info(f"Learned type mapping: '{text}' -> '{doc_type_code}'")


def match_material_type(material_type_text: str) -> Optional[str]:
    """将LLM返回的自由文本 material_type 映射到系统 DocType code。

    优先级: 旧版英文code精确匹配 > 用户学习映射精确匹配 > 关键词匹配。
    返回 DocType code 或 None。
    """
    if not material_type_text:
        return None

    text = material_type_text.strip()

    # 1) 精确匹配旧版英文code
    if text in _LEGACY_TYPE_TO_DOCTYPE:
        return _LEGACY_TYPE_TO_DOCTYPE[text]

    # 2) 用户确认的学习映射（精确匹配）
    learned = _get_learned_mappings()
    if text in learned:
        return learned[text]

    # 3) 关键词匹配中文描述（内置规则）
    for keywords, doc_type_code in _KEYWORD_DOCTYPE_RULES:
        for kw in keywords:
            if kw in text:
                return doc_type_code

    # 4) 用户自定义关键词规则（从settings加载）
    custom_rules = _get_custom_keyword_rules()
    for keywords, doc_type_code in custom_rules:
        for kw in keywords:
            if kw in text:
                return doc_type_code

    return None


def _get_custom_keyword_rules() -> list:
    """Load user-defined keyword→DocType rules from settings."""
    try:
        from dms_models import get_setting
        import json
        raw = get_setting("custom_keyword_rules")
        if raw:
            # Format: [{"keywords": ["关键词1","关键词2"], "doc_type_code": "my-type"}, ...]
            rules = json.loads(raw)
            return [(r["keywords"], r["doc_type_code"]) for r in rules if r.get("keywords") and r.get("doc_type_code")]
    except Exception:
        pass
    return []


def add_custom_keyword_rule(keywords: list[str], doc_type_code: str):
    """Add a user-defined keyword rule. Persisted in settings."""
    import json
    from dms_models import get_setting, set_setting
    raw = get_setting("custom_keyword_rules")
    rules = json.loads(raw) if raw else []
    # Avoid duplicate
    for r in rules:
        if r.get("doc_type_code") == doc_type_code:
            existing = set(r.get("keywords", []))
            existing.update(keywords)
            r["keywords"] = sorted(existing)
            set_setting("custom_keyword_rules", json.dumps(rules, ensure_ascii=False))
            return
    rules.append({"keywords": keywords, "doc_type_code": doc_type_code})
    set_setting("custom_keyword_rules", json.dumps(rules, ensure_ascii=False))


def remove_custom_keyword_rule(doc_type_code: str):
    """Remove a user-defined keyword rule by doc_type_code."""
    import json
    from dms_models import get_setting, set_setting
    raw = get_setting("custom_keyword_rules")
    if not raw:
        return
    rules = json.loads(raw)
    rules = [r for r in rules if r.get("doc_type_code") != doc_type_code]
    set_setting("custom_keyword_rules", json.dumps(rules, ensure_ascii=False))


def get_custom_keyword_rules_list() -> list[dict]:
    """Get all custom keyword rules as list of dicts."""
    try:
        from dms_models import get_setting
        import json
        raw = get_setting("custom_keyword_rules")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return []


def set_folder_mapping(doc_type_code: str, folder_path: str):
    """Add or update a DocType→Folder path mapping. Persisted in settings."""
    import json
    from dms_models import get_setting, set_setting
    raw = get_setting("custom_folder_mappings")
    mappings = json.loads(raw) if raw else {}
    mappings[doc_type_code] = folder_path
    set_setting("custom_folder_mappings", json.dumps(mappings, ensure_ascii=False))


def remove_folder_mapping(doc_type_code: str):
    """Remove a custom folder mapping."""
    import json
    from dms_models import get_setting, set_setting
    raw = get_setting("custom_folder_mappings")
    if not raw:
        return
    mappings = json.loads(raw)
    mappings.pop(doc_type_code, None)
    set_setting("custom_folder_mappings", json.dumps(mappings, ensure_ascii=False))


def _get_custom_folder_mappings() -> dict:
    """Load user-defined DocType→Folder mappings from settings."""
    try:
        from dms_models import get_setting
        import json
        raw = get_setting("custom_folder_mappings")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


# Keep backward-compatible name used elsewhere
MATERIAL_TYPE_TO_DOCTYPE = _LEGACY_TYPE_TO_DOCTYPE

_BUILTIN_FOLDER_PATHS = {
    "business-license": "/公司资质/营业执照/",
    "qualification-cert": "/公司资质/资质证书/",
    "iso-cert": "/公司资质/iso认证/",
    "honor-award": "/公司资质/荣誉奖项/",
    "id-card": "/人员资质/身份证件/",
    "education-cert": "/人员资质/学历证书/",
    "professional-cert": "/人员资质/职称证书/",
    "contract": "/业绩材料/合同/",
    "acceptance-report": "/业绩材料/验收报告/",
    "bid-document": "/投标文件/进行中/",
    "authorization": "/公司资质/授权文件/",
    "invoice": "/业绩材料/发票/",
    "product-brochure": "/公司资质/产品资料/",
    "company-profile": "/公司资质/公司简介/",
    "technical-doc": "/业绩材料/技术文档/",
}


def get_folder_path_for_doctype(doc_type_code: str) -> Optional[str]:
    """Get folder path for a DocType code (built-in + custom mappings)."""
    # Custom overrides built-in
    custom = _get_custom_folder_mappings()
    if doc_type_code in custom:
        return custom[doc_type_code]
    return _BUILTIN_FOLDER_PATHS.get(doc_type_code)


# Backward-compatible dict-like access for existing code
class _FolderPathProxy(dict):
    """Dict that merges built-in and custom folder mappings on .get()."""
    def get(self, key, default=None):
        return get_folder_path_for_doctype(key) or default

    def __contains__(self, key):
        return get_folder_path_for_doctype(key) is not None


DOCTYPE_TO_FOLDER_PATH = _FolderPathProxy(_BUILTIN_FOLDER_PATHS)


# Map legacy page_extraction_strategy material_type categories to LLM types
LLM_TYPE_TO_PAGE_STRATEGY = {
    "contract": "contract",
    "license": "company_business",
    "legal_person_cert": "company_business",
    "iso_cert": "iso_certificate",
    "qualification": "company_qualification",
    "id_card": "employee_document",
    "education": "employee_document",
    "certificate": "employee_document",
    "professional_cert": "employee_document",
    "honor": "other",
    "acceptance": "project_performance",
}


def _update_processing(doc_id: int, status: str, error: str = None, extra_meta: dict = None):
    """Update _processing status in document meta_json."""
    from dms_models import get_dms_session, DmsDocument

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return
        meta = {}
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        processing = meta.get("_processing", {})
        processing["status"] = status
        if error:
            processing["error"] = error
        if status == "completed":
            processing["completed_at"] = datetime.utcnow().isoformat()
        meta["_processing"] = processing

        if extra_meta:
            for k, v in extra_meta.items():
                if k != "_processing":
                    meta[k] = v

        doc.meta_json = json.dumps(meta, ensure_ascii=False)


def _get_original_file(doc_id: int):
    """Get the original file info for a document."""
    from dms_models import get_dms_session, DmsDocument, DmsFile

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return None
        cur_rev = doc.current_revision()
        if not cur_rev:
            return None
        for f in cur_rev.files:
            if f.file_type == "original":
                return {
                    "id": f.id,
                    "revision_id": f.revision_id,
                    "storage_path": f.storage_path,
                    "mime_type": f.mime_type or "",
                    "filename": f.filename,
                }
    return None


def _safe_remove_temp(path: str, retries: int = 3):
    """Remove a temp file with retries for Windows file-lock issues."""
    for i in range(retries):
        try:
            gc.collect()
            os.unlink(path)
            return
        except PermissionError:
            if i < retries - 1:
                time.sleep(0.5)
        except OSError:
            return


def _is_pdf(mime_type: str) -> bool:
    return mime_type == "application/pdf"


def _is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


def _is_word(mime_type: str) -> bool:
    return mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    )


# ============================================================
# Step 1: OCR
# ============================================================

def _run_ocr(doc_id: int, file_info: dict) -> Optional[str]:
    """Run OCR on the file. Returns combined OCR text or None."""
    from ocr_client import ocr_image, ocr_image_bytes, check_ocr_service
    from ocr_cache import get_cached_ocr, save_ocr_to_cache

    file_path = str(DATA_DIR / file_info["storage_path"])
    mime_type = file_info["mime_type"]

    if not check_ocr_service():
        raise RuntimeError("OCR service is not available")

    if _is_image(mime_type):
        # Single image OCR
        cached = get_cached_ocr(file_path, 0)
        if cached:
            return cached.get("text", "")
        text = ocr_image(file_path, page_number=1)
        if text:
            save_ocr_to_cache(file_path, 0, text)
        return text

    elif _is_pdf(mime_type):
        # PDF: render pages to PNG bytes in memory, OCR each
        import fitz  # PyMuPDF

        pdf_doc = fitz.open(file_path)
        total_pages = len(pdf_doc)
        all_text = []

        # For efficiency, OCR up to first 5 pages (or all if fewer)
        pages_to_ocr = min(total_pages, 5)

        for page_idx in range(pages_to_ocr):
            cached = get_cached_ocr(file_path, page_idx)
            if cached:
                all_text.append(cached.get("text", ""))
                continue

            page = pdf_doc[page_idx]
            pix = page.get_pixmap(dpi=200)

            # Downscale if image is too large for OCR API (max 4096px on long side, ~2MB)
            max_dim = 4096
            if pix.width > max_dim or pix.height > max_dim:
                scale = max_dim / max(pix.width, pix.height)
                scaled_dpi = int(200 * scale)
                logger.info(f"Page {page_idx} too large ({pix.width}x{pix.height}), rescaling to dpi={scaled_dpi}")
                pix = page.get_pixmap(dpi=scaled_dpi)

            png_bytes = pix.tobytes("png")

            text = ocr_image_bytes(png_bytes, page_number=page_idx + 1, label=f"doc{doc_id}_p{page_idx+1}")
            if text:
                save_ocr_to_cache(file_path, page_idx, text)
                all_text.append(text)

        pdf_doc.close()
        return "\n\n".join(all_text) if all_text else None

    return None


# ============================================================
# Step 2: LLM Classification
# ============================================================

def _run_llm_classification(doc_id: int, ocr_text: str, title: str) -> dict:
    """Run LLM classification. Returns extraction result dict."""
    from ocr_agent import intelligent_extract
    return intelligent_extract(ocr_text, material_title=title)


# ============================================================
# Step 3: DocType Auto-Mapping
# ============================================================

def _auto_assign_doc_type(doc_id: int, material_type: str):
    """Map material_type to DocType and assign to document (if not already set)."""
    from dms_models import get_dms_session, DmsDocument, DocType

    doc_type_code = match_material_type(material_type)
    if not doc_type_code:
        logger.info(f"No DocType mapping for material_type={material_type}")
        return

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return
        if doc.doc_type_id is not None:
            logger.info(f"Doc {doc_id} already has doc_type_id={doc.doc_type_id}, skipping auto-assign")
            return

        dt = session.query(DocType).filter(DocType.code == doc_type_code).first()
        if dt:
            doc.doc_type_id = dt.id
            logger.info(f"Auto-assigned DocType '{doc_type_code}' (id={dt.id}) to doc {doc_id}")


# ============================================================
# Step 4: Folder Auto-Filing
# ============================================================

def _auto_assign_folder(doc_id: int, doc_type_code: str = None):
    """Map DocType code to default folder and assign to document (if not already set)."""
    from dms_models import get_dms_session, DmsDocument, Folder, DocType

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return
        if doc.folder_id is not None:
            logger.info(f"Doc {doc_id} already has folder_id={doc.folder_id}, skipping auto-file")
            return

        # Determine doc_type_code from doc if not provided
        if not doc_type_code and doc.doc_type_id:
            dt = session.query(DocType).filter(DocType.id == doc.doc_type_id).first()
            if dt:
                doc_type_code = dt.code

        if not doc_type_code:
            return

        folder_path = DOCTYPE_TO_FOLDER_PATH.get(doc_type_code)
        if not folder_path:
            logger.info(f"No folder mapping for DocType code={doc_type_code}")
            return

        folder = session.query(Folder).filter(Folder.path == folder_path).first()
        if folder:
            doc.folder_id = folder.id
            logger.info(f"Auto-filed doc {doc_id} to folder '{folder_path}' (id={folder.id})")
        else:
            logger.warning(f"Target folder not found: {folder_path}")


# ============================================================
# Step 5: Entity Linking
# ============================================================

def _link_entities(doc_id: int, material_type: str, extracted_data: dict):
    """Create or match Entity and link to document."""
    from ocr_agent import create_entity_from_extraction
    from dms_models import get_dms_session, DmsDocument, Entity, DocumentEntity

    entity_info = create_entity_from_extraction(material_type, extracted_data)
    entity_type_raw = entity_info.get("entity_type")
    entity_data = entity_info.get("entity_data", {})

    if not entity_type_raw or not entity_data.get("name"):
        logger.info(f"No entity to link for doc {doc_id}")
        return

    # Map legacy entity_type to DMS entity_type
    dms_entity_type = "org" if entity_type_raw == "company" else "person"
    entity_name = entity_data["name"]

    with get_dms_session() as session:
        # Find or create entity
        entity = session.query(Entity).filter(
            Entity.entity_type == dms_entity_type,
            Entity.name == entity_name,
        ).first()

        if not entity:
            attrs = {k: v for k, v in entity_data.items() if k != "name"}
            entity = Entity(
                entity_type=dms_entity_type,
                name=entity_name,
                attributes=json.dumps(attrs, ensure_ascii=False) if attrs else None,
            )
            session.add(entity)
            session.flush()
            logger.info(f"Created entity: {dms_entity_type} '{entity_name}' (id={entity.id})")

        # Check if link already exists
        existing = session.query(DocumentEntity).filter(
            DocumentEntity.document_id == doc_id,
            DocumentEntity.entity_id == entity.id,
            DocumentEntity.role == "owner",
        ).first()

        if not existing:
            link = DocumentEntity(
                document_id=doc_id,
                entity_id=entity.id,
                role="owner",
            )
            session.add(link)
            logger.info(f"Linked entity '{entity_name}' to doc {doc_id}")


# ============================================================
# Step 6: Expiry Date
# ============================================================

def _set_expiry_date(doc_id: int, extracted_data: dict):
    """Extract and set expiry date on document."""
    from ocr_agent import extract_expiry_date
    from dms_models import get_dms_session, DmsDocument

    expiry_str = extract_expiry_date(extracted_data)
    if not expiry_str:
        return

    try:
        expiry = date.fromisoformat(expiry_str)
    except (ValueError, TypeError):
        logger.warning(f"Invalid expiry date format: {expiry_str}")
        return

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if doc:
            doc.expiry_date = expiry
            logger.info(f"Set expiry date for doc {doc_id}: {expiry_str}")


# ============================================================
# Step 7: PDF Page Extraction
# ============================================================

def _extract_pdf_pages(doc_id: int, file_info: dict, material_type: str = None):
    """Extract selected pages from PDF as extracted_page DmsFile records."""
    import fitz
    from dms_models import get_dms_session, DmsFile
    import hashlib

    file_path = str(DATA_DIR / file_info["storage_path"])
    revision_id = file_info["revision_id"]

    pdf_doc = fitz.open(file_path)
    total_pages = len(pdf_doc)

    # Determine which pages to extract
    strategy_type = LLM_TYPE_TO_PAGE_STRATEGY.get(material_type, "other") if material_type else "other"

    from page_extraction_strategy import get_pages_to_extract
    pages_config = get_pages_to_extract(strategy_type, total_pages)

    if not pages_config:
        # Fallback: extract first page
        pages_config = [{"page_num": 0, "section": "page", "material_type": "page", "title_suffix": "p1"}]

    rev_dir = DMS_FILES_DIR / str(doc_id) / str(revision_id)
    rev_dir.mkdir(parents=True, exist_ok=True)

    for config in pages_config:
        page_num = config["page_num"]
        # Handle -1 (last page)
        if page_num < 0:
            page_num = total_pages + page_num
        if page_num < 0 or page_num >= total_pages:
            continue

        page = pdf_doc[page_num]
        pix = page.get_pixmap(dpi=150)
        png_data = pix.tobytes("png")

        file_hash = hashlib.md5(png_data).hexdigest()
        filename = f"page_{page_num + 1}.png"
        safe_name = f"{file_hash[:8]}_{filename}"
        storage_path = f"dms_files/{doc_id}/{revision_id}/{safe_name}"
        full_path = DATA_DIR / storage_path

        with open(full_path, "wb") as f:
            f.write(png_data)

        with get_dms_session() as session:
            dms_file = DmsFile(
                revision_id=revision_id,
                file_type="extracted_page",
                filename=filename,
                storage_path=storage_path,
                mime_type="image/png",
                file_size=len(png_data),
                file_hash=file_hash,
                page_number=page_num + 1,
            )
            session.add(dms_file)

    pdf_doc.close()
    logger.info(f"Extracted {len(pages_config)} pages from PDF for doc {doc_id}")


# ============================================================
# Step 8: Thumbnail Generation
# ============================================================

def _generate_thumbnail(doc_id: int, file_info: dict):
    """Generate a thumbnail for the uploaded file."""
    from PIL import Image
    from dms_models import get_dms_session, DmsFile
    import hashlib
    import io

    file_path = str(DATA_DIR / file_info["storage_path"])
    mime_type = file_info["mime_type"]
    revision_id = file_info["revision_id"]

    thumb_data = None

    if _is_image(mime_type):
        try:
            img = Image.open(file_path)
            # Resize to 200px width maintaining aspect ratio
            w, h = img.size
            new_w = 200
            new_h = int(h * (new_w / w))
            img = img.resize((new_w, new_h), Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            thumb_data = buf.getvalue()
        except Exception as e:
            logger.warning(f"Failed to generate image thumbnail for doc {doc_id}: {e}")

    elif _is_pdf(mime_type):
        try:
            import fitz
            pdf_doc = fitz.open(file_path)
            if len(pdf_doc) > 0:
                page = pdf_doc[0]
                # Render at width ~200px
                zoom = 200.0 / page.rect.width
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                thumb_data = pix.tobytes("png")
            pdf_doc.close()
        except Exception as e:
            logger.warning(f"Failed to generate PDF thumbnail for doc {doc_id}: {e}")

    if not thumb_data:
        return

    file_hash = hashlib.md5(thumb_data).hexdigest()
    rev_dir = DMS_FILES_DIR / str(doc_id) / str(revision_id)
    rev_dir.mkdir(parents=True, exist_ok=True)

    filename = "thumbnail.png"
    safe_name = f"{file_hash[:8]}_{filename}"
    storage_path = f"dms_files/{doc_id}/{revision_id}/{safe_name}"
    full_path = DATA_DIR / storage_path

    with open(full_path, "wb") as f:
        f.write(thumb_data)

    with get_dms_session() as session:
        dms_file = DmsFile(
            revision_id=revision_id,
            file_type="thumbnail",
            filename=filename,
            storage_path=storage_path,
            mime_type="image/png",
            file_size=len(thumb_data),
            file_hash=file_hash,
        )
        session.add(dms_file)

    logger.info(f"Generated thumbnail for doc {doc_id} ({len(thumb_data)} bytes)")


# ============================================================
# Step 8: Version Matching
# ============================================================

def _try_version_match(doc_id: int, material_type: str) -> bool:
    """Try to match and merge with an existing document. Returns True if merged."""
    from dms_version_matcher import find_matching_document, is_newer_version, merge_as_revision
    from dms_models import get_dms_session, DmsDocument, DocumentEntity, DocType
    from dms_search import index_document

    doc_type_code = match_material_type(material_type)
    if not doc_type_code:
        return False

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return False

        # Get linked entity
        entity_link = (
            session.query(DocumentEntity)
            .filter(DocumentEntity.document_id == doc_id, DocumentEntity.role == "owner")
            .first()
        )
        if not entity_link:
            return False

        # Find matching existing document
        existing = find_matching_document(doc_id, entity_link.entity_id, doc_type_code, session)
        if not existing:
            return False

        # Check if new is actually newer
        is_newer, reason = is_newer_version(doc, existing)

        if is_newer:
            logger.info(f"Version match: doc {doc_id} is newer than doc {existing.id} ({reason})")
            success = merge_as_revision(existing.id, doc_id, session)
            if success:
                # Re-index the existing document with updated data
                try:
                    session.flush()
                except Exception:
                    pass
            return success
        else:
            # Not newer — add a note to meta_json about potential duplicate
            logger.info(f"Version match: doc {doc_id} is NOT newer than doc {existing.id} ({reason})")
            meta = {}
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            meta["_version_match"] = {
                "potential_duplicate_of": existing.id,
                "reason": reason,
            }
            doc.meta_json = json.dumps(meta, ensure_ascii=False)
            return False


# ============================================================
# Main Pipeline Orchestrator
# ============================================================

def analyze_document(doc_id: int):
    """Phase 1: Pre-analysis. Runs in background thread after upload.

    Generates page thumbnails, detects text vs scanned pages, extracts text.
    Pauses at 'analysis_done' for human to select OCR pages.
    """
    logger.info(f"Starting pre-analysis for doc {doc_id}")
    try:
        _update_processing(doc_id, "analyzing")

        file_info = _get_original_file(doc_id)
        if not file_info:
            _update_processing(doc_id, "failed", error="No original file found")
            return

        mime_type = file_info["mime_type"]

        # Word files: skip analysis, go straight to completed
        if _is_word(mime_type):
            logger.info(f"Doc {doc_id} is Word file, skipping analysis")
            try:
                from dms_search import index_document
                index_document(doc_id)
            except Exception as e:
                logger.warning(f"FTS indexing failed for doc {doc_id}: {e}")
            _update_processing(doc_id, "completed")
            return

        # Generate main thumbnail (for queue display)
        try:
            _generate_thumbnail(doc_id, file_info)
        except Exception as e:
            logger.warning(f"Thumbnail generation failed for doc {doc_id}: {e}")

        # Run document pre-analysis
        from doc_analyzer import analyze_document as run_analysis
        analysis = run_analysis(doc_id)

        if "error" in analysis:
            _update_processing(doc_id, "failed", error=analysis["error"])
            return

        # Store analysis results and pause for human input
        _update_processing(doc_id, "analysis_done", extra_meta={"_analysis": analysis})
        logger.info(f"Pre-analysis complete for doc {doc_id}: {analysis['total_pages']} pages, "
                     f"{len(analysis.get('ocr_pages', []))} need OCR")

    except Exception as e:
        logger.error(f"Pre-analysis failed for doc {doc_id}: {e}", exc_info=True)
        _update_processing(doc_id, "failed", error=str(e))


def run_ocr_phase(doc_id: int, page_numbers: list[int] = None, ocr_provider_override: str = None):
    """Phase 2: Selective OCR. Called after human selects pages.

    Args:
        page_numbers: Specific pages to OCR (0-indexed). If None, uses suggested pages.
        ocr_provider_override: Temporarily use a different OCR provider for this run.
    """
    logger.info(f"Starting OCR phase for doc {doc_id}, pages={page_numbers}, provider={ocr_provider_override}")
    try:
        _update_processing(doc_id, "ocr_running")

        # Get analysis data to determine pages
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as session:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                _update_processing(doc_id, "failed", error="Document not found")
                return
            meta = {}
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                except (json.JSONDecodeError, TypeError):
                    pass

        analysis = meta.get("_analysis", {})

        if page_numbers is None:
            page_numbers = analysis.get("suggested_ocr_pages", analysis.get("ocr_pages", []))

        # Run selective OCR
        from doc_analyzer import run_selective_ocr
        ocr_results = run_selective_ocr(doc_id, page_numbers, ocr_provider_override=ocr_provider_override)

        # Merge OCR text with existing analysis text
        all_text_parts = []

        # Collect text from text-based pages (from analysis)
        for page_info in analysis.get("pages", []):
            if page_info.get("has_text") and page_info.get("text"):
                all_text_parts.append((page_info["page_num"], page_info["text"]))

        # Add OCR results
        for page_num, text in ocr_results.items():
            all_text_parts.append((page_num, text))

        # Sort by page number and combine
        all_text_parts.sort(key=lambda x: x[0])
        combined_text = "\n\n".join(text for _, text in all_text_parts)

        # Update analysis with OCR results
        analysis["ocr_results"] = {str(k): v for k, v in ocr_results.items()}
        analysis["combined_text"] = combined_text

        # Update pages that were OCR'd
        for page_info in analysis.get("pages", []):
            pn = page_info["page_num"]
            if pn in ocr_results:
                page_info["ocr_text"] = ocr_results[pn]
                page_info["needs_ocr"] = False

        _update_processing(doc_id, "ocr_done", extra_meta={"_analysis": analysis})
        logger.info(f"OCR phase complete for doc {doc_id}: {len(ocr_results)} pages OCR'd")

    except Exception as e:
        logger.error(f"OCR phase failed for doc {doc_id}: {e}", exc_info=True)
        _update_processing(doc_id, "failed", error=str(e))


def run_classify_phase(doc_id: int):
    """Phase 3: LLM classification. Can be triggered after OCR or directly if text-based.

    Pauses at 'classified' for human review.
    """
    logger.info(f"Starting classification phase for doc {doc_id}")
    try:
        _update_processing(doc_id, "classifying")

        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as session:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                _update_processing(doc_id, "failed", error="Document not found")
                return
            doc_title = doc.title or ""
            meta = {}
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                except (json.JSONDecodeError, TypeError):
                    pass

        analysis = meta.get("_analysis", {})
        combined_text = analysis.get("combined_text") or analysis.get("full_text") or ""

        if not combined_text:
            logger.warning(f"No text available for classification of doc {doc_id}")
            _update_processing(doc_id, "classified", extra_meta={
                "material_type": "unknown",
                "confidence": 0,
                "extracted_data": {},
                "summary": "",
            })
            return

        # Run LLM classification
        extraction = _run_llm_classification(doc_id, combined_text, doc_title)

        material_type = extraction.get("material_type", "unknown")
        extracted_data = extraction.get("extracted_data", {})
        confidence = extraction.get("confidence", 0)

        # Store classification results — pause for human review
        _update_processing(doc_id, "classified", extra_meta={
            "material_type": material_type,
            "confidence": confidence,
            "extracted_data": extracted_data,
            "summary": extraction.get("summary", ""),
        })

        # Auto-suggest doc_type and folder based on classification
        doc_type_code = match_material_type(material_type)
        if doc_type_code:
            from dms_models import get_dms_session, DocType, Folder
            with get_dms_session() as session:
                dt = session.query(DocType).filter(DocType.code == doc_type_code).first()
                folder_path = DOCTYPE_TO_FOLDER_PATH.get(doc_type_code)
                folder = session.query(Folder).filter(Folder.path == folder_path).first() if folder_path else None

                suggestion = {}
                if dt:
                    suggestion["suggested_doc_type"] = {"id": dt.id, "name": dt.name, "code": dt.code}
                if folder:
                    suggestion["suggested_folder"] = {"id": folder.id, "name": folder.name, "path": folder.path}

                if suggestion:
                    _update_processing(doc_id, "classified", extra_meta=suggestion)

        logger.info(f"Classification complete for doc {doc_id}: type={material_type}, confidence={confidence}")

    except Exception as e:
        logger.error(f"Classification phase failed for doc {doc_id}: {e}", exc_info=True)
        _update_processing(doc_id, "failed", error=str(e))


def finalize_document(doc_id: int):
    """Phase 4: Finalize after human approval. Runs entity linking, expiry, version match, etc."""
    logger.info(f"Finalizing doc {doc_id}")
    try:
        _update_processing(doc_id, "finalizing")

        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as session:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if not doc:
                return
            meta = {}
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            pre_set_doc_type = doc.doc_type_id is not None
            pre_set_folder = doc.folder_id is not None

        material_type = meta.get("material_type", "unknown")
        extracted_data = meta.get("extracted_data", {})

        file_info = _get_original_file(doc_id)
        mime_type = file_info["mime_type"] if file_info else ""

        # Auto-assign doc_type if not already set
        if not pre_set_doc_type and material_type != "unknown":
            _auto_assign_doc_type(doc_id, material_type)

        # Auto-assign folder if not already set
        if not pre_set_folder:
            doc_type_code = match_material_type(material_type)
            _auto_assign_folder(doc_id, doc_type_code)

        # Entity linking
        try:
            _link_entities(doc_id, material_type, extracted_data)
        except Exception as e:
            logger.warning(f"Entity linking failed for doc {doc_id}: {e}")

        # Expiry date
        try:
            _set_expiry_date(doc_id, extracted_data)
        except Exception as e:
            logger.warning(f"Expiry date extraction failed for doc {doc_id}: {e}")

        # Version matching
        try:
            merged = _try_version_match(doc_id, material_type)
            if merged:
                logger.info(f"Doc {doc_id} merged as new revision via version matching")
                return
        except Exception as e:
            logger.warning(f"Version matching failed for doc {doc_id}: {e}")

        # PDF page extraction
        if file_info and _is_pdf(mime_type):
            try:
                _extract_pdf_pages(doc_id, file_info, material_type)
            except Exception as e:
                logger.warning(f"PDF page extraction failed for doc {doc_id}: {e}")

        # FTS index
        try:
            from dms_search import index_document
            index_document(doc_id)
        except Exception as e:
            logger.warning(f"FTS indexing failed for doc {doc_id}: {e}")

        _update_processing(doc_id, "completed")
        logger.info(f"Finalization complete for doc {doc_id}")

    except Exception as e:
        logger.error(f"Finalization failed for doc {doc_id}: {e}", exc_info=True)
        _update_processing(doc_id, "failed", error=str(e))


def process_document(doc_id: int):
    """Legacy: Full auto pipeline (for backward compatibility).

    Runs all phases automatically without human pause points.
    """
    logger.info(f"Starting full auto-processing pipeline for doc {doc_id}")

    try:
        file_info = _get_original_file(doc_id)
        if not file_info:
            _update_processing(doc_id, "failed", error="No original file found")
            return

        mime_type = file_info["mime_type"]

        # Word files: skip OCR/LLM, just index by title and complete
        if _is_word(mime_type):
            logger.info(f"Doc {doc_id} is Word file, skipping OCR/LLM")
            try:
                from dms_search import index_document
                index_document(doc_id)
            except Exception as e:
                logger.warning(f"FTS indexing failed for doc {doc_id}: {e}")
            _update_processing(doc_id, "completed")
            return

        # Get document title for LLM context
        from dms_models import get_dms_session, DmsDocument
        with get_dms_session() as session:
            doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            doc_title = doc.title if doc else ""
            pre_set_doc_type = doc.doc_type_id is not None if doc else False
            pre_set_folder = doc.folder_id is not None if doc else False

        # Step 1: Thumbnail generation (do this early so UI has something to show)
        try:
            _generate_thumbnail(doc_id, file_info)
        except Exception as e:
            logger.warning(f"Thumbnail generation failed for doc {doc_id}: {e}")
            # Non-fatal, continue

        # Step 2: OCR
        _update_processing(doc_id, "ocr_running")
        ocr_text = _run_ocr(doc_id, file_info)

        if not ocr_text:
            logger.warning(f"OCR returned no text for doc {doc_id}")
            _update_processing(doc_id, "failed", error="OCR未能识别出文本，可能是图片过大、格式不支持或OCR服务异常")
            return

        # Step 3: LLM Classification
        _update_processing(doc_id, "classifying")
        extraction = _run_llm_classification(doc_id, ocr_text, doc_title)

        material_type = extraction.get("material_type", "unknown")
        extracted_data = extraction.get("extracted_data", {})
        confidence = extraction.get("confidence", 0)

        # Store extraction results in meta_json
        _update_processing(doc_id, "classifying", extra_meta={
            "material_type": material_type,
            "confidence": confidence,
            "extracted_data": extracted_data,
            "summary": extraction.get("summary", ""),
        })

        # Step 4: DocType auto-mapping (if not pre-set)
        if not pre_set_doc_type and material_type != "unknown":
            _auto_assign_doc_type(doc_id, material_type)

        # Step 5: Folder auto-filing (if not pre-set)
        if not pre_set_folder:
            doc_type_code = match_material_type(material_type)
            _auto_assign_folder(doc_id, doc_type_code)

        # Step 6: Entity linking
        _update_processing(doc_id, "linking_entities")
        try:
            _link_entities(doc_id, material_type, extracted_data)
        except Exception as e:
            logger.warning(f"Entity linking failed for doc {doc_id}: {e}")

        # Step 7: Expiry date
        try:
            _set_expiry_date(doc_id, extracted_data)
        except Exception as e:
            logger.warning(f"Expiry date extraction failed for doc {doc_id}: {e}")

        # Step 8: Version matching (after entity linking + expiry date are set)
        try:
            merged = _try_version_match(doc_id, material_type)
            if merged:
                # Document was merged into an existing one — we're done
                logger.info(f"Doc {doc_id} merged as new revision via version matching")
                return
        except Exception as e:
            logger.warning(f"Version matching failed for doc {doc_id}: {e}")

        # Step 9: PDF page extraction
        if _is_pdf(mime_type):
            try:
                _extract_pdf_pages(doc_id, file_info, material_type)
            except Exception as e:
                logger.warning(f"PDF page extraction failed for doc {doc_id}: {e}")

        # Step 10: Index document in FTS
        try:
            from dms_search import index_document
            index_document(doc_id)
        except Exception as e:
            logger.warning(f"FTS indexing failed for doc {doc_id}: {e}")

        # Done
        _update_processing(doc_id, "completed")
        logger.info(f"Processing complete for doc {doc_id}: type={material_type}, confidence={confidence}")

    except Exception as e:
        logger.error(f"Processing pipeline failed for doc {doc_id}: {e}", exc_info=True)
        _update_processing(doc_id, "failed", error=str(e))

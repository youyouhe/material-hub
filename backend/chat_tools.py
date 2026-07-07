"""
Chat Agent Tools - Functions that the LLM can call during conversation.

Provides document search, detail retrieval, OCR text reading, and statistics
so the LLM agent can answer deep questions about document contents.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from dms_models import get_dms_session, DmsDocument, Folder, DocType, Entity, DocumentEntity

logger = logging.getLogger("materialhub.chat_tools")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))

# ============================================================
# Tool Definitions (OpenAI function-calling format)
# ============================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "全文搜索文档。按关键词查找，返回匹配的文档标题、类型、摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "最大返回数，默认10", "default": 10}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_detail",
            "description": "获取文档完整详情（元数据、AI提取字段、实体关联、附件列表）。",
            "parameters": {
                "type": "object",
                "properties": {"doc_id": {"type": "integer", "description": "文档ID"}},
                "required": ["doc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_document_content",
            "description": "读取文档的OCR全文内容。用于深入了解合同条款、财务数据、证书详情等。",
            "parameters": {
                "type": "object",
                "properties": {"doc_id": {"type": "integer", "description": "文档ID"}},
                "required": ["doc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "按条件筛选文档列表。支持按文件夹、类型、状态过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_id": {"type": "integer", "description": "文件夹ID，含子文件夹"},
                    "doc_type": {"type": "string", "description": "文档类型名，如'营业执照'"},
                    "status": {"type": "string", "description": "状态: active/draft/expired/archived"},
                    "limit": {"type": "integer", "description": "每页最大返回数，默认20", "default": 20},
                    "offset": {"type": "integer", "description": "分页偏移量，默认0。设为20获取第二页", "default": 0}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "聚合统计：按类型/状态/文件夹分布、到期文档、实体概要。",
            "parameters": {
                "type": "object",
                "properties": {"folder_id": {"type": "integer", "description": "限定范围到指定文件夹"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_doc_types",
            "description": "列出系统所有可用的文档类型及其分类。用于了解有哪些文档类型可选。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_folder",
            "description": "浏览文件夹结构。不传参数返回完整文件夹树；传路径返回该文件夹下的文档。",
            "parameters": {
                "type": "object",
                "properties": {"folder_path": {"type": "string", "description": "文件夹路径，如'/公司资质/'，留空查看整棵树"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_folder_mappings",
            "description": "列出文档类型→文件夹的自动归档映射关系。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_document",
            "description": "更新文档的分类、标题、状态等。用于重新分类或修正信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "integer", "description": "文档ID"},
                    "title": {"type": "string", "description": "新标题（留空不修改）"},
                    "doc_type_code": {"type": "string", "description": "新文档类型代码，如'business-license'（留空不修改）"},
                    "folder_path": {"type": "string", "description": "新文件夹路径，如'/公司资质/营业执照/'（留空不修改）"},
                    "status": {"type": "string", "description": "新状态: active/draft/expired/archived（留空不修改）"},
                    "expiry_date": {"type": "string", "description": "到期日 YYYY-MM-DD（留空不修改）"}
                },
                "required": ["doc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_folder_mapping",
            "description": "设置文档类型→文件夹的自动归档映射。",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type_code": {"type": "string", "description": "文档类型代码，如'business-license'"},
                    "folder_path": {"type": "string", "description": "目标文件夹路径，如'/公司资质/营业执照/'"}
                },
                "required": ["doc_type_code", "folder_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "创建新文件夹。用于组织文档分类时添加文件夹。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "文件夹名称，如'会议记录'"},
                    "parent_path": {"type": "string", "description": "父文件夹路径，如'/公司资质/'。留空则创建在根目录"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_folder",
            "description": "重命名文件夹或移动文件夹。",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "当前文件夹路径，如'/公司资质/产品资料/'"},
                    "new_name": {"type": "string", "description": "新名称（可选）"},
                    "new_parent_path": {"type": "string", "description": "新父文件夹路径（可选，用于移动文件夹）"}
                },
                "required": ["folder_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_folder",
            "description": "删除空文件夹。不会删除包含文档的文件夹。",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "要删除的文件夹路径，如'/公司资质/旧文件夹/'"}
                },
                "required": ["folder_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_doc_type",
            "description": "创建新的文档类型。当系统缺少某个分类时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "类型中文名，如'完税证明'"},
                    "code": {"type": "string", "description": "类型代码(英文)，如'tax-payment-cert'"},
                    "category": {"type": "string", "description": "所属类别: company/personnel/project/bid/general", "default": "company"},
                    "description": {"type": "string", "description": "描述（可选）"}
                },
                "required": ["name", "code", "category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_entities",
            "description": "列出公司或人员实体。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "'org' (公司) 或 'person' (人员)"},
                    "q": {"type": "string", "description": "名称搜索"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_deep_search",
            "description": "深度语义+知识图谱搜索。能理解查询意图，通过实体关系进行多跳推理，找到关键词搜索找不到的隐藏关联文档。适合复杂问题如'持有ISO证书的公司签了哪些合同'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言问题"},
                    "mode": {"type": "string", "description": "搜索模式: vector(语义)/hybrid(混合)/multihop(多跳推理,默认)"},
                    "limit": {"type": "integer", "description": "返回数量，默认10"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kb_graph_explore",
            "description": "探索公司或人员的知识图谱。查看其关联实体、相关事件、和在文档中的出现情况。用于理解某个实体的完整上下文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string", "description": "公司名称或人员姓名"},
                    "depth": {"type": "integer", "description": "探索深度(1-3)，默认1"}
                },
                "required": ["entity_name"]
            }
        }
    },
]


# ============================================================
# Tool Execution
# ============================================================

def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name and return the result as a string."""
    try:
        if name == "search_documents":
            return _tool_search_documents(**arguments)
        elif name == "get_document_detail":
            return _tool_get_document_detail(**arguments)
        elif name == "read_document_content":
            return _tool_read_document_content(**arguments)
        elif name == "list_documents":
            return _tool_list_documents(**arguments)
        elif name == "get_statistics":
            return _tool_get_statistics(**arguments)
        elif name == "list_doc_types":
            return _tool_list_doc_types(**arguments)
        elif name == "browse_folder":
            return _tool_browse_folder(**arguments)
        elif name == "list_folder_mappings":
            return _tool_list_folder_mappings(**arguments)
        elif name == "update_document":
            return _tool_update_document(**arguments)
        elif name == "set_folder_mapping":
            return _tool_set_folder_mapping(**arguments)
        elif name == "list_entities":
            return _tool_list_entities(**arguments)
        elif name == "create_doc_type":
            return _tool_create_doc_type(**arguments)
        elif name == "create_folder":
            return _tool_create_folder(**arguments)
        elif name == "update_folder":
            return _tool_update_folder(**arguments)
        elif name == "delete_folder":
            return _tool_delete_folder(**arguments)
        elif name == "kb_deep_search":
            return _tool_kb_deep_search(**arguments)
        elif name == "kb_graph_explore":
            return _tool_kb_graph_explore(**arguments)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Tool execution error ({name}): {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tool_search_documents(query: str, limit: int = 10) -> str:
    """FTS search for documents."""
    from dms_search import search_index

    fts = search_index(query, limit=limit)
    if not fts["doc_ids"]:
        return json.dumps({"results": [], "message": f"No documents found for '{query}'"}, ensure_ascii=False)

    results = []
    with get_dms_session() as session:
        docs = session.query(DmsDocument).filter(
            DmsDocument.id.in_(fts["doc_ids"])
        ).all()
        for doc in docs:
            item = {
                "id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "doc_type": doc.doc_type.name if doc.doc_type else None,
                "folder": doc.folder.path if doc.folder else None,
                "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            }
            # Add snippet if available
            detail = fts["details"].get(doc.id, {})
            if detail.get("snippet"):
                item["snippet"] = detail["snippet"]
            # Add summary
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                    if meta.get("summary"):
                        item["summary"] = meta["summary"]
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(item)

    return json.dumps({"results": results, "total": len(results)}, ensure_ascii=False)


def _tool_get_document_detail(doc_id: int) -> str:
    """Get full document metadata."""
    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return json.dumps({"error": f"Document {doc_id} not found"}, ensure_ascii=False)

        result = {
            "id": doc.id,
            "title": doc.title,
            "status": doc.status,
            "doc_type": doc.doc_type.name if doc.doc_type else None,
            "folder": doc.folder.path if doc.folder else None,
            "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }

        # Entities
        entities = []
        for link in doc.entity_links:
            if link.entity:
                e = {"name": link.entity.name, "type": link.entity.entity_type, "role": link.role}
                if link.entity.attributes:
                    try:
                        e["attributes"] = json.loads(link.entity.attributes)
                    except (json.JSONDecodeError, TypeError):
                        pass
                entities.append(e)
        result["entities"] = entities

        # Tags
        result["tags"] = [tl.tag.name for tl in doc.tag_links if tl.tag]

        # Metadata (summary, extracted_data, ASR text preview, etc)
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json) if isinstance(doc.meta_json, str) else doc.meta_json
                if not isinstance(meta, dict):
                    meta = {}
                result["summary"] = meta.get("summary", "")
                result["material_type"] = meta.get("material_type", "")
                result["confidence"] = meta.get("confidence", 0)
                result["extracted_data"] = meta.get("extracted_data", {})
                result["has_ocr"] = bool(meta.get("summary") or meta.get("extracted_data"))

                # ASR transcript preview (first 300 chars) for audio/video documents
                asr_text = meta.get("asr_text", "")
                if asr_text:
                    result["is_audio_video"] = True
                    result["asr_preview"] = asr_text[:300] + ("..." if len(asr_text) > 300 else "")
                    result["asr_full_length"] = len(asr_text)
                    # Auto-set material_type if empty (so agent has a hint)
                    if not result.get("material_type"):
                        result["material_type"] = "语音/视频转录"

                # Word document text preview
                word_text = meta.get("word_text", "")
                if word_text:
                    result["is_word_doc"] = True
                    result["content_preview"] = word_text[:300] + ("..." if len(word_text) > 300 else "")
                    result["word_full_length"] = len(word_text)
            except (json.JSONDecodeError, TypeError):
                pass

        # File info
        cur_rev = doc.current_revision()
        if cur_rev:
            result["files"] = [
                {"filename": f.filename, "type": f.file_type, "mime": f.mime_type, "size": f.file_size}
                for f in cur_rev.files
            ]

        return json.dumps(result, ensure_ascii=False)


def _tool_read_document_content(doc_id: int) -> str:
    """Read full OCR text from cache for a document."""
    from ocr_cache import get_cached_ocr

    with get_dms_session() as session:
        doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return json.dumps({"error": f"Document {doc_id} not found"}, ensure_ascii=False)

        cur_rev = doc.current_revision()
        if not cur_rev:
            return json.dumps({"error": "No current revision"}, ensure_ascii=False)

        orig_file = None
        for f in cur_rev.files:
            if f.file_type == "original":
                orig_file = f
                break

        if not orig_file:
            return json.dumps({"error": "No original file found"}, ensure_ascii=False)

        file_path = str(DATA_DIR / orig_file.storage_path)

        # Try reading all cached OCR pages
        pages_text = []
        for page_idx in range(50):  # max 50 pages
            cached = get_cached_ocr(file_path, page_idx)
            if cached is None:
                break
            text = cached.get("text", "")
            if text:
                pages_text.append(f"=== Page {page_idx + 1} ===\n{text}")

        if not pages_text:
            # Fallback: try ASR transcript (audio/video) or extracted_data from metadata
            fallback = ""
            source_type = "metadata_only"
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json) if isinstance(doc.meta_json, str) else doc.meta_json
                    if not isinstance(meta, dict):
                        meta = {}

                    # Priority 1: ASR transcript (audio/video documents)
                    asr_text = meta.get("asr_text", "")
                    if asr_text:
                        # Truncate to protect context (first 2000 chars ≈ 1000 tokens)
                        truncated = asr_text[:2000]
                        if len(asr_text) > 2000:
                            truncated += f"\n\n... [转录文本共 {len(asr_text)} 字，已截断显示前 2000 字]"
                        fallback = f"=== ASR 转录 (语音转文字) ===\n{truncated}"
                        source_type = "asr_transcript"
                    elif meta.get("word_text"):
                        # Priority 1b: Word document extracted text
                        word_text = meta.get("word_text", "")
                        truncated = word_text[:2000]
                        if len(word_text) > 2000:
                            truncated += f"\n\n... [文档共 {len(word_text)} 字，已截断显示前 2000 字]"
                        fallback = f"=== Word 文档文本 ===\n{truncated}"
                        source_type = "word_text"
                    else:
                        # Priority 2: summary + extracted_data
                        summary = meta.get("summary", "")
                        extracted = meta.get("extracted_data", {})
                        parts = []
                        if summary:
                            parts.append(f"Summary: {summary}")
                        if extracted:
                            parts.append("Extracted fields:")
                            for k, v in extracted.items():
                                if v:
                                    parts.append(f"  {k}: {v}")
                        fallback = "\n".join(parts)
                except (json.JSONDecodeError, TypeError):
                    pass

            if fallback:
                return json.dumps({
                    "doc_id": doc_id,
                    "title": doc.title,
                    "source": source_type,
                    "note": "语音/视频文档的转录文本" if source_type == "asr_transcript"
                            else "OCR text not in cache, only metadata available.",
                    "content": fallback
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "doc_id": doc_id,
                    "title": doc.title,
                    "error": "No text available. The document may need OCR/ASR processing first."
                }, ensure_ascii=False)

        # Truncate if too long (keep within reasonable token limits)
        full_text = "\n\n".join(pages_text)
        if len(full_text) > 8000:
            full_text = full_text[:8000] + "\n\n... [truncated, showing first 8000 characters]"

        return json.dumps({
            "doc_id": doc_id,
            "title": doc.title,
            "pages": len(pages_text),
            "source": "ocr_cache",
            "content": full_text
        }, ensure_ascii=False)


def _tool_list_documents(folder_id: int = None, doc_type: str = None,
                         status: str = None, limit: int = 20, offset: int = 0) -> str:
    """List documents with filters."""
    with get_dms_session() as session:
        query = session.query(DmsDocument)

        if folder_id:
            # Include subfolders
            folder = session.query(Folder).filter(Folder.id == folder_id).first()
            if folder:
                sub_ids = {r[0] for r in session.query(Folder.id).filter(
                    Folder.path.like(f"{folder.path}%")
                ).all()}
                query = query.filter(DmsDocument.folder_id.in_(sub_ids))

        if doc_type:
            dt = session.query(DocType).filter(DocType.name.like(f"%{doc_type}%")).first()
            if dt:
                query = query.filter(DmsDocument.doc_type_id == dt.id)

        if status:
            query = query.filter(DmsDocument.status == status)

        total = query.count()
        docs = query.order_by(DmsDocument.updated_at.desc()).offset(offset).limit(limit).all()

        results = []
        for doc in docs:
            item = {
                "id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "doc_type": doc.doc_type.name if doc.doc_type else None,
                "folder": doc.folder.path if doc.folder else None,
                "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            }
            # Brief metadata indicator
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json) if isinstance(doc.meta_json, str) else doc.meta_json
                    if not isinstance(meta, dict):
                        meta = {}
                    ed = meta.get("extracted_data", {})
                    item["has_metadata"] = bool(ed and isinstance(ed, dict) and len(ed) > 0)
                    if meta.get("summary"):
                        item["summary"] = meta["summary"][:100]
                    # Mark audio/video docs with content preview
                    asr = meta.get("asr_text", "")
                    if asr:
                        item["media_type"] = "audio_video"
                        item["content_preview"] = asr[:150] + ("..." if len(asr) > 150 else "")
                except (json.JSONDecodeError, TypeError):
                    item["has_metadata"] = False
            results.append(item)

        has_more = (offset + len(results)) < total
        resp = {"results": results, "total": total, "offset": offset, "limit": limit, "showing": len(results)}
        if has_more:
            resp["next_offset"] = offset + len(results)
        return json.dumps(resp, ensure_ascii=False)


def _tool_get_statistics(folder_id: int = None) -> str:
    """Get aggregate statistics."""
    from datetime import date, timedelta

    with get_dms_session() as session:
        base_query = session.query(DmsDocument)
        scope_label = "all"

        if folder_id:
            folder = session.query(Folder).filter(Folder.id == folder_id).first()
            if folder:
                sub_ids = {r[0] for r in session.query(Folder.id).filter(
                    Folder.path.like(f"{folder.path}%")
                ).all()}
                base_query = base_query.filter(DmsDocument.folder_id.in_(sub_ids))
                scope_label = folder.path

        all_docs = base_query.all()
        total = len(all_docs)

        # By status
        status_counts = {}
        for doc in all_docs:
            status_counts[doc.status] = status_counts.get(doc.status, 0) + 1

        # By type
        type_counts = {}
        for doc in all_docs:
            tname = doc.doc_type.name if doc.doc_type else "uncategorized"
            type_counts[tname] = type_counts.get(tname, 0) + 1

        # By folder
        folder_counts = {}
        for doc in all_docs:
            fname = doc.folder.path if doc.folder else "unfiled"
            folder_counts[fname] = folder_counts.get(fname, 0) + 1

        # Expiring soon (within 90 days)
        today = date.today()
        cutoff = today + timedelta(days=90)
        expiring = []
        expired = []
        for doc in all_docs:
            if doc.expiry_date:
                if doc.expiry_date < today:
                    expired.append({"id": doc.id, "title": doc.title, "expiry_date": doc.expiry_date.isoformat()})
                elif doc.expiry_date <= cutoff:
                    expiring.append({"id": doc.id, "title": doc.title, "expiry_date": doc.expiry_date.isoformat()})

        # Metadata coverage
        with_metadata = 0
        without_metadata = 0
        for doc in all_docs:
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
                    ed = meta.get("extracted_data", {})
                    if ed and isinstance(ed, dict) and len(ed) > 0:
                        with_metadata += 1
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
            without_metadata += 1

        # Entities
        entity_count = session.query(Entity).count()

        return json.dumps({
            "scope": scope_label,
            "total_documents": total,
            "by_status": status_counts,
            "by_type": type_counts,
            "by_folder": folder_counts,
            "metadata_coverage": {"with_metadata": with_metadata, "without_metadata": without_metadata},
            "expiring_within_90_days": expiring,
            "already_expired": expired,
            "total_entities": entity_count,
        }, ensure_ascii=False)


def _tool_list_doc_types(**kwargs) -> str:
    """List all doc types."""
    with get_dms_session() as s:
        types = s.query(DocType).order_by(DocType.category, DocType.name).all()
        result = {}
        for dt in types:
            cat = dt.category or "other"
            if cat not in result:
                result[cat] = []
            result[cat].append({"id": dt.id, "name": dt.name, "code": dt.code, "description": dt.description})
        return json.dumps({"doc_types": result, "total": len(types)}, ensure_ascii=False)


def _tool_browse_folder(folder_path: str = "", limit: int = 30, offset: int = 0, **kwargs) -> str:
    """Browse folder tree or list docs in a folder."""
    with get_dms_session() as s:
        if not folder_path:
            # Return tree
            roots = s.query(Folder).filter(Folder.parent_id.is_(None)).order_by(Folder.sort_order).all()

            def _build_tree(nodes):
                result = []
                for n in nodes:
                    children = s.query(Folder).filter(Folder.parent_id == n.id).order_by(Folder.sort_order).all()
                    node = {"id": n.id, "name": n.name, "path": n.path}
                    if children:
                        node["children"] = _build_tree(children)
                    result.append(node)
                return result

            return json.dumps({"tree": _build_tree(roots)}, ensure_ascii=False)

        # Find folder and list docs
        folder = s.query(Folder).filter(
            (Folder.path == folder_path) | (Folder.name == folder_path)
        ).first()
        if not folder:
            return json.dumps({"error": f"Folder not found: {folder_path}"}, ensure_ascii=False)

        doc_query = s.query(DmsDocument).filter(
            DmsDocument.folder_id == folder.id,
            DmsDocument.status.in_(["active", "draft"])
        ).order_by(DmsDocument.updated_at.desc())
        total = doc_query.count()
        docs = doc_query.offset(offset).limit(limit).all()

        results = []
        for d in docs:
            results.append({
                "id": d.id, "title": d.title, "status": d.status,
                "doc_type": d.doc_type.name if d.doc_type else None,
                "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None,
            })
        has_more = (offset + len(results)) < total
        resp = {"folder": folder.path, "documents": results, "total": total, "offset": offset, "limit": limit}
        if has_more:
            resp["next_offset"] = offset + len(results)
        return json.dumps(resp, ensure_ascii=False)


def _tool_list_folder_mappings(**kwargs) -> str:
    """List doc_type → folder mappings."""
    from dms_processor import _BUILTIN_FOLDER_PATHS, _get_custom_folder_mappings
    with get_dms_session() as s:
        types = {dt.code: dt.name for dt in s.query(DocType).all()}

    mappings = []
    for code, path in _BUILTIN_FOLDER_PATHS.items():
        mappings.append({"doc_type_code": code, "doc_type_name": types.get(code, code),
                         "folder_path": path, "source": "builtin"})
    for code, path in _get_custom_folder_mappings().items():
        # Override builtin
        for m in mappings:
            if m["doc_type_code"] == code:
                m["folder_path"] = path
                m["source"] = "custom"
                break
        else:
            mappings.append({"doc_type_code": code, "doc_type_name": types.get(code, code),
                             "folder_path": path, "source": "custom"})
    return json.dumps({"mappings": mappings}, ensure_ascii=False)


def _tool_update_document(doc_id: int, title: str = "", doc_type_code: str = "",
                          folder_path: str = "", status: str = "", expiry_date: str = "", **kwargs) -> str:
    """Update document metadata."""
    with get_dms_session() as s:
        doc = s.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
        if not doc:
            return json.dumps({"error": f"Document {doc_id} not found"}, ensure_ascii=False)

        if title:
            doc.title = title
        if status and status in ("active", "draft", "expired", "archived"):
            doc.status = status
        if expiry_date:
            from datetime import date as dt_date
            try:
                doc.expiry_date = dt_date.fromisoformat(expiry_date)
            except ValueError:
                pass
        if doc_type_code:
            dt = s.query(DocType).filter(DocType.code == doc_type_code).first()
            if dt:
                doc.doc_type_id = dt.id
        if folder_path:
            folder = s.query(Folder).filter(
                (Folder.path == folder_path) | (Folder.name == folder_path)
            ).first()
            if folder:
                doc.folder_id = folder.id

        s.flush()
        return json.dumps({
            "success": True, "doc_id": doc.id, "title": doc.title, "status": doc.status,
            "doc_type": doc.doc_type.name if doc.doc_type else None,
            "folder": doc.folder.path if doc.folder else None,
            "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
        }, ensure_ascii=False)


def _tool_set_folder_mapping(doc_type_code: str, folder_path: str, **kwargs) -> str:
    """Set a doc_type → folder mapping."""
    from dms_processor import set_folder_mapping
    with get_dms_session() as s:
        if not s.query(DocType).filter(DocType.code == doc_type_code).first():
            return json.dumps({"error": f"DocType '{doc_type_code}' not found"}, ensure_ascii=False)
    set_folder_mapping(doc_type_code, folder_path)
    return json.dumps({"success": True, "doc_type_code": doc_type_code, "folder_path": folder_path}, ensure_ascii=False)


def _tool_list_entities(type: str = "", q: str = "", limit: int = 30, offset: int = 0, **kwargs) -> str:
    """List entities (org/person)."""
    from dms_models import Entity
    with get_dms_session() as s:
        query = s.query(Entity)
        if type:
            query = query.filter(Entity.entity_type == type)
        if q:
            query = query.filter(Entity.name.ilike(f"%{q}%"))
        total = query.count()
        entities = query.order_by(Entity.name).offset(offset).limit(limit).all()
        results = []
        for e in entities:
            attrs = {}
            if e.attributes:
                try:
                    attrs = json.loads(e.attributes)
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append({"id": e.id, "name": e.name, "entity_type": e.entity_type, "attributes": attrs})
        has_more = (offset + len(results)) < total
        resp = {"results": results, "total": total, "offset": offset, "limit": limit}
        if has_more:
            resp["next_offset"] = offset + len(results)
        return json.dumps(resp, ensure_ascii=False)


def _tool_create_doc_type(name: str, code: str, category: str = "company",
                          description: str = "", **kwargs) -> str:
    """Create a new document type."""
    valid_categories = {"company", "personnel", "project", "bid", "general"}
    if category not in valid_categories:
        return json.dumps({"error": f"Invalid category '{category}'. Must be one of: {valid_categories}"}, ensure_ascii=False)

    with get_dms_session() as s:
        if s.query(DocType).filter(DocType.code == code).first():
            return json.dumps({"error": f"DocType code '{code}' already exists"}, ensure_ascii=False)
        if s.query(DocType).filter(DocType.name == name).first():
            return json.dumps({"error": f"DocType name '{name}' already exists"}, ensure_ascii=False)

        dt = DocType(name=name, code=code, category=category, description=description or None)
        s.add(dt)
        s.flush()

        # Auto-create folder mapping if a matching folder exists
        from dms_processor import set_folder_mapping
        folder = s.query(Folder).filter(Folder.name == name).first()
        if folder:
            set_folder_mapping(code, folder.path)

        return json.dumps({
            "success": True, "id": dt.id, "name": dt.name, "code": dt.code,
            "category": dt.category, "auto_mapped": bool(folder),
        }, ensure_ascii=False)


# ============================================================
# KB Tools (Phase 4)
# ============================================================

# ============================================================
# Folder CRUD Tools
# ============================================================

def _tool_create_folder(name: str, parent_path: str = "", **kwargs) -> str:
    """Create a new folder."""
    with get_dms_session() as s:
        # Resolve parent
        parent_id = None
        if parent_path:
            parent = s.query(Folder).filter(Folder.path == parent_path).first()
            if not parent:
                # Try by name
                parent = s.query(Folder).filter(Folder.name == parent_path).first()
            if not parent:
                return json.dumps({"error": f"父文件夹不存在: {parent_path}"}, ensure_ascii=False)
            parent_id = parent.id

        # Check duplicate
        existing = s.query(Folder).filter(
            Folder.name == name, Folder.parent_id == parent_id
        ).first()
        if existing:
            return json.dumps({
                "success": True, "id": existing.id, "name": existing.name,
                "path": existing.path, "note": "folder already exists",
            }, ensure_ascii=False)

        # Build path
        if parent:
            base_path = parent.path.rstrip("/") + "/" + name + "/"
        else:
            base_path = "/" + name + "/"

        folder = Folder(name=name, parent_id=parent_id, path=base_path)
        s.add(folder)
        s.flush()

        return json.dumps({
            "success": True, "id": folder.id, "name": folder.name, "path": folder.path,
        }, ensure_ascii=False)


def _tool_update_folder(folder_path: str, new_name: str = "", new_parent_path: str = "", **kwargs) -> str:
    """Rename or move a folder."""
    with get_dms_session() as s:
        folder = s.query(Folder).filter(Folder.path == folder_path).first()
        if not folder:
            folder = s.query(Folder).filter(Folder.name == folder_path).first()
        if not folder:
            return json.dumps({"error": f"文件夹不存在: {folder_path}"}, ensure_ascii=False)

        updated = False

        if new_name and new_name != folder.name:
            # Update name + path for this folder and all children
            old_base = folder.path
            new_base = old_base.rsplit(folder.name, 1)[0] + new_name + "/"
            folder.name = new_name
            folder.path = new_base
            # Update children paths
            for child in s.query(Folder).filter(Folder.path.like(old_base + "%")).all():
                child.path = new_base + child.path[len(old_base):]
            updated = True

        if new_parent_path:
            new_parent = s.query(Folder).filter(Folder.path == new_parent_path).first()
            if not new_parent:
                new_parent = s.query(Folder).filter(Folder.name == new_parent_path).first()
            if new_parent and new_parent.id != folder.parent_id:
                old_base = folder.path
                folder.parent_id = new_parent.id
                new_base = new_parent.path.rstrip("/") + "/" + folder.name + "/"
                folder.path = new_base
                for child in s.query(Folder).filter(Folder.path.like(old_base + "%")).all():
                    child.path = new_base + child.path[len(old_base):]
                updated = True

        if updated:
            s.commit()
            return json.dumps({
                "success": True, "id": folder.id, "name": folder.name, "path": folder.path,
            }, ensure_ascii=False)
        return json.dumps({"success": False, "note": "no changes"}, ensure_ascii=False)


def _tool_delete_folder(folder_path: str, **kwargs) -> str:
    """Delete an empty folder."""
    with get_dms_session() as s:
        folder = s.query(Folder).filter(Folder.path == folder_path).first()
        if not folder:
            folder = s.query(Folder).filter(Folder.name == folder_path).first()
        if not folder:
            return json.dumps({"error": f"文件夹不存在: {folder_path}"}, ensure_ascii=False)

        # Check if folder contains documents
        doc_count = s.query(DmsDocument).filter(DmsDocument.folder_id == folder.id).count()
        child_count = s.query(Folder).filter(Folder.parent_id == folder.id).count()
        if doc_count > 0 or child_count > 0:
            return json.dumps({
                "error": f"文件夹非空: {doc_count} 个文档, {child_count} 个子文件夹, 请先清空后再删除",
            }, ensure_ascii=False)

        s.delete(folder)
        s.commit()
        return json.dumps({"success": True, "deleted": folder_path}, ensure_ascii=False)


def _tool_kb_deep_search(query: str, mode: str = "multihop", limit: int = 10, **kwargs) -> str:
    """Deep semantic + knowledge graph search."""
    try:
        import requests as req
        api_base = "http://localhost:8201"
        url = f"{api_base}/api/v2/kb/search/multihop" if mode == "multihop" else f"{api_base}/api/v2/kb/search"
        params = {"q": query, "top_k": min(limit, 20)}
        if mode == "multihop":
            params["max_hops"] = 2

        resp = req.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"KB search failed: {e}"}, ensure_ascii=False)

    results = data.get("results", [])
    items = []
    for r in results:
        items.append({
            "doc_id": r.get("doc_id"),
            "title": r.get("title"),
            "score": r.get("score", 0),
            "doc_type": r.get("doc_type", ""),
            "content_preview": (r.get("content") or "")[:300],
            "entities": r.get("entity_names", []),
        })

    response = {"results": items, "total": len(items), "mode": mode}
    if data.get("trace"):
        response["search_steps"] = [
            {"step": s["step"], "name": s["name"], "result": s["detail"]}
            for s in data["trace"]["steps"]
        ]
        response["entities_found"] = data["trace"]["entities_found"]
        response["events_found"] = data["trace"]["events_found"]

    return json.dumps(response, ensure_ascii=False)


def _tool_kb_graph_explore(entity_name: str, depth: int = 1, **kwargs) -> str:
    """Explore knowledge graph around an entity."""
    try:
        import requests as req
        api_base = "http://localhost:8201"
        resp = req.get(
            f"{api_base}/api/v2/kb/entities/{entity_name}/graph",
            params={"depth": depth},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"Graph explore failed: {e}"}, ensure_ascii=False)

    if "error" in data:
        return json.dumps(data, ensure_ascii=False)

    return json.dumps({
        "entity": data["entity"],
        "related_entities": data.get("related_entities", []),
        "relations": data.get("relations", []),
        "events": data.get("events", []),
    }, ensure_ascii=False)

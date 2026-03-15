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
            "description": "Search documents by keyword. Returns matching document titles, types, and snippets. Use this when the user asks to find specific documents or mentions keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword(s), e.g. '营业执照', '资质证书', '审计报告'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_detail",
            "description": "Get full metadata and extracted information for a specific document by ID. Use this when you need detailed info about a specific document (extracted fields, entity links, expiry date, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "integer",
                        "description": "Document ID"
                    }
                },
                "required": ["doc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_document_content",
            "description": "Read the full OCR text content of a document. Use this when the user asks about specific content, data, or details inside a document (e.g. financial figures, contract clauses, certificate details). This returns the raw OCR text from the document pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "integer",
                        "description": "Document ID"
                    }
                },
                "required": ["doc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List documents with optional filters. Use this for browsing, filtering by folder/type/status, or getting an overview of available documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "integer",
                        "description": "Filter by folder ID (includes subfolders)"
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "Filter by document type name, e.g. '营业执照', '资质证书'"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status: active/draft/expired/archived"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "Get aggregate statistics: document counts by type, folder, status; expiring documents; entity summary. Use this for overview/summary questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "integer",
                        "description": "Optional: scope stats to a specific folder"
                    }
                },
                "required": []
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

        # Metadata (summary, extracted_data, etc)
        if doc.meta_json:
            try:
                meta = json.loads(doc.meta_json)
                result["summary"] = meta.get("summary", "")
                result["material_type"] = meta.get("material_type", "")
                result["confidence"] = meta.get("confidence", 0)
                result["extracted_data"] = meta.get("extracted_data", {})
                result["has_ocr"] = bool(meta.get("summary") or meta.get("extracted_data"))
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
            # Fallback: try extracted_data from metadata
            fallback = ""
            if doc.meta_json:
                try:
                    meta = json.loads(doc.meta_json)
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
                    "source": "metadata_only",
                    "note": "Full OCR text not available in cache. Only metadata summary is available.",
                    "content": fallback
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "doc_id": doc_id,
                    "title": doc.title,
                    "error": "No OCR text available. The document may need to be processed first (OCR + AI analysis)."
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
                         status: str = None, limit: int = 20) -> str:
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
        docs = query.order_by(DmsDocument.updated_at.desc()).limit(limit).all()

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
                    meta = json.loads(doc.meta_json)
                    ed = meta.get("extracted_data", {})
                    item["has_metadata"] = bool(ed and isinstance(ed, dict) and len(ed) > 0)
                    if meta.get("summary"):
                        item["summary"] = meta["summary"][:100]
                except (json.JSONDecodeError, TypeError):
                    item["has_metadata"] = False
            results.append(item)

        return json.dumps({"results": results, "total": total, "showing": len(results)}, ensure_ascii=False)


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

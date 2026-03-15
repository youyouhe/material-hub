"""DMS Unified Search and FTS Index Management API."""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Request

from dms_models import (
    get_dms_session, DmsDocument, DocumentEntity, DocumentTag, Folder, DocType,
)
from dms_search import search_index, rebuild_index
from dms_auth import get_accessible_folder_ids

logger = logging.getLogger("materialhub.routers.v2_search")

router = APIRouter(prefix="/api/v2/search", tags=["dms-search"])


def _format_result(doc: DmsDocument, snippet: str = None) -> dict:
    """Format a document for search results."""
    # Get thumbnail URL
    thumbnail_url = None
    cur_rev = doc.current_revision()
    if cur_rev:
        for f in cur_rev.files:
            if f.file_type == "thumbnail":
                thumbnail_url = f"/api/v2/files/{f.id}"
                break

    # Get entity names
    entity_names = [
        link.entity.name for link in doc.entity_links
        if link.entity and link.entity.name
    ]

    return {
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "doc_type": {"id": doc.doc_type.id, "name": doc.doc_type.name, "code": doc.doc_type.code} if doc.doc_type else None,
        "folder": {"id": doc.folder.id, "name": doc.folder.name, "path": doc.folder.path} if doc.folder else None,
        "entity_names": entity_names,
        "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
        "thumbnail_url": thumbnail_url,
        "snippet": snippet,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


@router.get("")
async def search(
    request: Request,
    q: Optional[str] = Query(None),
    folder_id: Optional[int] = Query(None),
    doc_type_id: Optional[int] = Query(None),
    entity_id: Optional[int] = Query(None),
    tag_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    expiry_before: Optional[str] = Query(None),
    expiry_after: Optional[str] = Query(None),
    sort: str = Query("relevance"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Unified search with keyword (FTS) and faceted filtering."""
    allowed_folders = get_accessible_folder_ids(request)

    if q and q.strip():
        return _keyword_search(
            q.strip(), folder_id, doc_type_id, entity_id, tag_id,
            status, expiry_before, expiry_after, sort, limit, offset,
            allowed_folders=allowed_folders,
        )
    else:
        return _facet_search(
            folder_id, doc_type_id, entity_id, tag_id,
            status, expiry_before, expiry_after, sort, limit, offset,
            allowed_folders=allowed_folders,
        )


def _keyword_search(
    q, folder_id, doc_type_id, entity_id, tag_id,
    status, expiry_before, expiry_after, sort, limit, offset,
    *, allowed_folders=None,
):
    """Search using FTS5 with BM25 ranking, then apply SQL facet filters."""
    # Get FTS matches (fetch more than needed since we'll filter)
    fts_limit = limit + offset + 200  # over-fetch for post-filtering
    fts_result = search_index(q, limit=fts_limit, offset=0)
    matched_ids = fts_result["doc_ids"]
    details = fts_result["details"]

    if not matched_ids:
        return {"results": [], "total": 0, "limit": limit, "offset": offset}

    with get_dms_session() as session:
        query = session.query(DmsDocument).filter(DmsDocument.id.in_(matched_ids))

        # Apply facet filters
        query = _apply_facets(query, folder_id, doc_type_id, entity_id, tag_id,
                              status, expiry_before, expiry_after,
                              allowed_folders=allowed_folders, session=session)

        total = query.count()

        # Sort by FTS rank (preserve FTS order) or other criteria
        if sort == "date":
            docs = query.order_by(DmsDocument.updated_at.desc()).offset(offset).limit(limit).all()
        elif sort == "title":
            docs = query.order_by(DmsDocument.title).offset(offset).limit(limit).all()
        else:
            # Relevance: preserve FTS rank order
            docs_all = query.all()
            # Sort by FTS rank
            docs_all.sort(key=lambda d: details.get(d.id, {}).get("rank", 0))
            docs = docs_all[offset:offset + limit]

        results = []
        for doc in docs:
            snippet = details.get(doc.id, {}).get("snippet")
            results.append(_format_result(doc, snippet=snippet))

        return {"results": results, "total": total, "limit": limit, "offset": offset}


def _facet_search(
    folder_id, doc_type_id, entity_id, tag_id,
    status, expiry_before, expiry_after, sort, limit, offset,
    *, allowed_folders=None,
):
    """Search using SQL filters only (no keyword)."""
    with get_dms_session() as session:
        query = session.query(DmsDocument)

        query = _apply_facets(query, folder_id, doc_type_id, entity_id, tag_id,
                              status, expiry_before, expiry_after,
                              allowed_folders=allowed_folders, session=session)

        total = query.count()

        # Sort
        if sort == "title":
            query = query.order_by(DmsDocument.title)
        else:
            query = query.order_by(DmsDocument.updated_at.desc())

        docs = query.offset(offset).limit(limit).all()
        results = [_format_result(doc) for doc in docs]

        return {"results": results, "total": total, "limit": limit, "offset": offset}


def _apply_facets(query, folder_id, doc_type_id, entity_id, tag_id,
                  status, expiry_before, expiry_after, *, allowed_folders=None,
                  session=None):
    """Apply facet filters to a query."""
    # Folder-level access control
    if allowed_folders is not None:
        if not allowed_folders:
            # User has no folder access — return nothing
            query = query.filter(DmsDocument.id == -1)
        else:
            query = query.filter(DmsDocument.folder_id.in_(allowed_folders))

    if folder_id is not None and session is not None:
        # Include sub-folders
        folder = session.query(Folder).filter(Folder.id == folder_id).first()
        if folder:
            sub_ids = [r[0] for r in session.query(Folder.id).filter(
                Folder.path.like(f"{folder.path}%")
            ).all()]
            query = query.filter(DmsDocument.folder_id.in_(sub_ids))
        else:
            query = query.filter(DmsDocument.folder_id == folder_id)
    elif folder_id is not None:
        query = query.filter(DmsDocument.folder_id == folder_id)

    if doc_type_id is not None:
        query = query.filter(DmsDocument.doc_type_id == doc_type_id)

    if status:
        if status == "expired":
            today = date.today()
            query = query.filter(
                (DmsDocument.status == "expired") |
                ((DmsDocument.expiry_date.isnot(None)) & (DmsDocument.expiry_date < today))
            )
        else:
            query = query.filter(DmsDocument.status == status)

    if entity_id is not None:
        query = query.join(DocumentEntity).filter(DocumentEntity.entity_id == entity_id)

    if tag_id is not None:
        query = query.join(DocumentTag).filter(DocumentTag.tag_id == tag_id)

    if expiry_before:
        try:
            d = date.fromisoformat(expiry_before)
            query = query.filter(DmsDocument.expiry_date <= d)
        except ValueError:
            pass

    if expiry_after:
        try:
            d = date.fromisoformat(expiry_after)
            query = query.filter(DmsDocument.expiry_date >= d)
        except ValueError:
            pass

    return query


@router.post("/rebuild-index")
async def rebuild_search_index():
    """Rebuild the entire FTS search index from all active/draft documents."""
    count = rebuild_index()
    return {"indexed_count": count}

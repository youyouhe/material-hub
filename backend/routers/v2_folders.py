"""DMS Folder (File Cabinet) API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from dms_models import get_dms_session, Folder, DmsDocument, recompute_subtree_paths, _slugify
from dms_auth import require_role, get_current_user_id, get_accessible_folder_ids

logger = logging.getLogger("materialhub.routers.v2_folders")

router = APIRouter(prefix="/api/v2/folders", tags=["dms-folders"])


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


def _build_tree(folders: list, parent_id=None, doc_counts: dict = None) -> list:
    """Convert flat folder list into nested tree structure with document counts."""
    tree = []
    for f in folders:
        if f.parent_id == parent_id:
            node = f.to_dict()
            node["children"] = _build_tree(folders, f.id, doc_counts)
            node["doc_count"] = doc_counts.get(f.id, 0) if doc_counts else 0
            tree.append(node)
    tree.sort(key=lambda x: x["sort_order"])
    return tree


@router.get("/tree")
async def get_folder_tree(request: Request):
    """Get full folder tree as nested structure, filtered by user access."""
    allowed_folders = get_accessible_folder_ids(request)

    with get_dms_session() as session:
        query = session.query(Folder)
        if allowed_folders is not None:
            if not allowed_folders:
                return {"tree": []}
            query = query.filter(Folder.id.in_(allowed_folders))
        folders = query.order_by(Folder.sort_order).all()

        # Count documents per folder in one query
        from sqlalchemy import func
        counts = session.query(
            DmsDocument.folder_id, func.count(DmsDocument.id)
        ).filter(
            DmsDocument.folder_id.isnot(None)
        ).group_by(DmsDocument.folder_id).all()
        doc_counts = {folder_id: cnt for folder_id, cnt in counts}

        return {"tree": _build_tree(folders, doc_counts=doc_counts)}


@router.get("/{folder_id}/tree")
async def get_subtree(folder_id: int):
    """Get a folder and all its descendants as a nested tree."""
    with get_dms_session() as session:
        root = session.query(Folder).filter(Folder.id == folder_id).first()
        if not root:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Get all descendants via path prefix
        all_folders = session.query(Folder).filter(
            Folder.path.like(f"{root.path}%")
        ).order_by(Folder.sort_order).all()

        # Include root itself
        if root not in all_folders:
            all_folders.insert(0, root)

        result = root.to_dict()
        result["children"] = _build_tree(all_folders, root.id)
        return result


@router.post("/", dependencies=[require_role("admin")])
async def create_folder(data: FolderCreate, request: Request):
    """Create a new folder."""
    with get_dms_session() as session:
        parent = None
        if data.parent_id:
            parent = session.query(Folder).filter(Folder.id == data.parent_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent folder not found")

        folder = Folder(
            name=data.name,
            parent_id=data.parent_id,
            description=data.description,
            sort_order=data.sort_order,
            created_by=get_current_user_id(request),
        )

        # Compute path
        slug = _slugify(data.name)
        if parent:
            folder.path = f"{parent.path}{slug}/"
        else:
            folder.path = f"/{slug}/"

        # Check path uniqueness
        existing = session.query(Folder).filter(Folder.path == folder.path).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Folder path '{folder.path}' already exists")

        session.add(folder)
        session.flush()
        return folder.to_dict()


@router.patch("/{folder_id}", dependencies=[require_role("admin")])
async def update_folder(folder_id: int, data: FolderUpdate):
    """Update folder fields or move to new parent."""
    with get_dms_session() as session:
        folder = session.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        update_data = data.model_dump(exclude_unset=True)

        needs_path_recompute = False

        if "parent_id" in update_data:
            new_parent_id = update_data["parent_id"]
            if new_parent_id == folder_id:
                raise HTTPException(status_code=400, detail="Cannot set folder as its own parent")
            if new_parent_id:
                new_parent = session.query(Folder).filter(Folder.id == new_parent_id).first()
                if not new_parent:
                    raise HTTPException(status_code=404, detail="New parent folder not found")
                # Prevent moving into own subtree
                if new_parent.path.startswith(folder.path):
                    raise HTTPException(status_code=400, detail="Cannot move folder into its own subtree")
                folder.parent = new_parent
            else:
                folder.parent_id = None
                folder.parent = None
            needs_path_recompute = True

        if "name" in update_data:
            folder.name = update_data["name"]
            needs_path_recompute = True

        if "description" in update_data:
            folder.description = update_data["description"]

        if "sort_order" in update_data:
            folder.sort_order = update_data["sort_order"]

        if needs_path_recompute:
            recompute_subtree_paths(session, folder)

        session.flush()
        return folder.to_dict()


@router.post("/reorder", dependencies=[require_role("admin")])
async def reorder_folders(data: dict):
    """Batch update sort_order for sibling folders.

    Body: { "parent_id": null | int, "order": [id1, id2, id3, ...] }
    Sets sort_order = index for each folder ID in the given order.
    """
    parent_id = data.get("parent_id")  # null for root
    order = data.get("order", [])
    if not order:
        raise HTTPException(status_code=400, detail="order list is required")

    with get_dms_session() as session:
        for idx, folder_id in enumerate(order):
            folder = session.query(Folder).filter(
                Folder.id == folder_id,
                Folder.parent_id == parent_id,
            ).first()
            if folder:
                folder.sort_order = idx
        return {"success": True}


@router.delete("/{folder_id}", dependencies=[require_role("admin")])
async def delete_folder(folder_id: int):
    """Delete a folder (must be empty)."""
    with get_dms_session() as session:
        folder = session.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Check for child folders
        child_count = session.query(Folder).filter(Folder.parent_id == folder_id).count()
        if child_count > 0:
            raise HTTPException(status_code=409, detail=f"Folder has {child_count} child folder(s). Delete them first.")

        # Check for documents
        doc_count = session.query(DmsDocument).filter(DmsDocument.folder_id == folder_id).count()
        if doc_count > 0:
            raise HTTPException(status_code=409, detail=f"Folder contains {doc_count} document(s). Move or delete them first.")

        session.delete(folder)
        return {"success": True, "deleted": folder.name}

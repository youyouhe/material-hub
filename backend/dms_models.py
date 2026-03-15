"""
DMS (Document Management System) core data models.
New normalized schema replacing the legacy flat Material model.
"""

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Date, Boolean,
    ForeignKey, Text, UniqueConstraint, event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

logger = logging.getLogger("materialhub.dms_models")

DmsBase = declarative_base()


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    # Transliterate common Chinese folder names to pinyin-like slugs
    # For non-ASCII, just use the name as-is (URL-encoded in practice)
    slug = name.strip().lower()
    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug or 'untitled'


# ============================================================
# Folder (File Cabinet)
# ============================================================

class Folder(DmsBase):
    __tablename__ = "dms_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("dms_folders.id"), nullable=True)
    path = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = relationship("Folder", remote_side=[id], backref="children")
    documents = relationship("DmsDocument", back_populates="folder")

    def compute_path(self):
        """Compute materialized path from parent chain."""
        slug = _slugify(self.name)
        if self.parent:
            return f"{self.parent.path}{slug}/"
        return f"/{slug}/"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "path": self.path,
            "description": self.description,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# DocType (Document Type Configuration)
# ============================================================

class DocType(DmsBase):
    __tablename__ = "dms_doc_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    code = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=False)  # company/personnel/project/bid/general
    metadata_schema = Column(Text, nullable=True)  # JSON schema defining custom fields
    icon = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("DmsDocument", back_populates="doc_type")

    def to_dict(self):
        import json
        schema = None
        if self.metadata_schema:
            try:
                schema = json.loads(self.metadata_schema)
            except (json.JSONDecodeError, TypeError):
                schema = self.metadata_schema
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "category": self.category,
            "metadata_schema": schema,
            "icon": self.icon,
            "description": self.description,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# Document (Logical Document)
# ============================================================

VALID_STATUS_TRANSITIONS = {
    "draft": {"active"},
    "active": {"expired", "archived"},
    "expired": {"archived"},
    "archived": set(),
}


class DmsDocument(DmsBase):
    __tablename__ = "dms_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_id = Column(Integer, ForeignKey("dms_folders.id"), nullable=True)
    doc_type_id = Column(Integer, ForeignKey("dms_doc_types.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="draft")  # draft/active/expired/archived
    meta_json = Column("metadata", Text, nullable=True)  # JSON, type-specific fields
    expiry_date = Column(Date, nullable=True)
    created_by = Column(Integer, nullable=True)
    locked_by = Column(Integer, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    folder = relationship("Folder", back_populates="documents")
    doc_type = relationship("DocType", back_populates="documents")
    revisions = relationship("Revision", back_populates="document", cascade="all, delete-orphan",
                             order_by="Revision.version_number.desc()")
    entity_links = relationship("DocumentEntity", back_populates="document", cascade="all, delete-orphan")
    tag_links = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan")

    def can_transition_to(self, new_status: str) -> bool:
        allowed = VALID_STATUS_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    def current_revision(self):
        for rev in self.revisions:
            if rev.is_current:
                return rev
        return None

    def to_dict(self, include_revision=True, include_relations=True):
        import json
        meta = None
        if self.meta_json:
            try:
                meta = json.loads(self.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass

        result = {
            "id": self.id,
            "folder_id": self.folder_id,
            "doc_type_id": self.doc_type_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "metadata": meta,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_revision:
            cur = self.current_revision()
            result["current_revision"] = cur.to_dict() if cur else None

        if include_relations:
            result["folder"] = {"id": self.folder.id, "name": self.folder.name, "path": self.folder.path} if self.folder else None
            result["doc_type"] = {"id": self.doc_type.id, "name": self.doc_type.name, "code": self.doc_type.code} if self.doc_type else None
            result["entities"] = [el.to_dict() for el in self.entity_links]
            result["tags"] = [tl.to_dict() for tl in self.tag_links]

        return result


# ============================================================
# Revision (Document Version)
# ============================================================

class Revision(DmsBase):
    __tablename__ = "dms_revisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("dms_documents.id"), nullable=False)
    version_number = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)
    change_note = Column(String, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("DmsDocument", back_populates="revisions")
    files = relationship("DmsFile", back_populates="revision", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "version_number": self.version_number,
            "is_current": self.is_current,
            "change_note": self.change_note,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "files": [f.to_dict() for f in self.files],
        }


# ============================================================
# File (Physical File)
# ============================================================

class DmsFile(DmsBase):
    __tablename__ = "dms_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    revision_id = Column(Integer, ForeignKey("dms_revisions.id"), nullable=False)
    file_type = Column(String, nullable=False)  # original/thumbnail/extracted_page/ocr_result
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)  # relative path from DATA_DIR
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, default=0)
    file_hash = Column(String, nullable=True, index=True)
    page_number = Column(Integer, nullable=True)  # for extracted_page type
    created_at = Column(DateTime, default=datetime.utcnow)

    revision = relationship("Revision", back_populates="files")

    def to_dict(self):
        return {
            "id": self.id,
            "revision_id": self.revision_id,
            "file_type": self.file_type,
            "filename": self.filename,
            "storage_path": self.storage_path,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "page_number": self.page_number,
            "url": f"/api/v2/files/{self.id}",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# Entity (Unified Organization / Person)
# ============================================================

class Entity(DmsBase):
    __tablename__ = "dms_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String, nullable=False)  # org/person
    name = Column(String, nullable=False)
    attributes = Column(Text, nullable=True)  # JSON, type-specific fields
    parent_id = Column(Integer, ForeignKey("dms_entities.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = relationship("Entity", remote_side=[id], backref="children_entities")
    document_links = relationship("DocumentEntity", back_populates="entity", cascade="all, delete-orphan")

    def to_dict(self):
        import json
        attrs = None
        if self.attributes:
            try:
                attrs = json.loads(self.attributes)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "name": self.name,
            "attributes": attrs,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# DocumentEntity (Document-Entity Association)
# ============================================================

class DocumentEntity(DmsBase):
    __tablename__ = "dms_document_entities"
    __table_args__ = (
        UniqueConstraint("document_id", "entity_id", "role", name="uq_doc_entity_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("dms_documents.id"), nullable=False)
    entity_id = Column(Integer, ForeignKey("dms_entities.id"), nullable=False)
    role = Column(String, nullable=False)  # owner/issuer/subject/related
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("DmsDocument", back_populates="entity_links")
    entity = relationship("Entity", back_populates="document_links")

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "entity_id": self.entity_id,
            "entity_name": self.entity.name if self.entity else None,
            "entity_type": self.entity.entity_type if self.entity else None,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# Tag
# ============================================================

class Tag(DmsBase):
    __tablename__ = "dms_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document_links = relationship("DocumentTag", back_populates="tag", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# DocumentTag (Document-Tag Association)
# ============================================================

class DocumentTag(DmsBase):
    __tablename__ = "dms_document_tags"
    __table_args__ = (
        UniqueConstraint("document_id", "tag_id", name="uq_doc_tag"),
    )

    document_id = Column(Integer, ForeignKey("dms_documents.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("dms_tags.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("DmsDocument", back_populates="tag_links")
    tag = relationship("Tag", back_populates="document_links")

    def to_dict(self):
        return {
            "tag_id": self.tag_id,
            "tag_name": self.tag.name if self.tag else None,
            "tag_color": self.tag.color if self.tag else None,
        }


# ============================================================
# DMS Database Session Management
# ============================================================

_dms_engine = None
_DmsSessionLocal = None


def init_dms_db(db_path: str = None):
    """Initialize DMS tables. Call after legacy init_db()."""
    global _dms_engine, _DmsSessionLocal

    if db_path is None:
        db_path = os.getenv("DB_PATH", "data/materials.db")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _dms_engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(_dms_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    DmsBase.metadata.create_all(_dms_engine)
    _DmsSessionLocal = sessionmaker(bind=_dms_engine)
    logger.info("DMS tables initialized at %s", db_path)

    # Migration: add locked_by/locked_at to dms_documents if missing
    from sqlalchemy import text, inspect as sa_inspect
    with _dms_engine.connect() as conn:
        tables = sa_inspect(_dms_engine).get_table_names()
        if "dms_documents" in tables:
            result = conn.execute(text("PRAGMA table_info(dms_documents)"))
            columns = [row[1] for row in result]
            if "locked_by" not in columns:
                conn.execute(text("ALTER TABLE dms_documents ADD COLUMN locked_by INTEGER"))
                conn.commit()
            if "locked_at" not in columns:
                conn.execute(text("ALTER TABLE dms_documents ADD COLUMN locked_at TIMESTAMP"))
                conn.commit()

    # Initialize FTS5 search index table
    from dms_search import init_fts_table
    init_fts_table()


@contextmanager
def get_dms_session():
    """Get a DMS database session."""
    if _DmsSessionLocal is None:
        init_dms_db()
    session: Session = _DmsSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================
# UserFolderAccess (Folder-level permission per user)
# ============================================================

class UserFolderAccess(DmsBase):
    """Maps users to folders they are allowed to access.
    Admin users bypass this table (full access).
    If a user has zero rows, they see nothing.
    Access to a folder implicitly includes all its sub-folders.
    """
    __tablename__ = "dms_user_folder_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("dms_folders.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    folder = relationship("Folder")

    __table_args__ = (
        UniqueConstraint("user_id", "folder_id", name="uq_user_folder"),
    )


# ============================================================
# ApiAgent (Token-based agent for MCP / external integrations)
# ============================================================

class ApiAgent(DmsBase):
    """API agents with token-based auth and folder-level permissions.
    Used by MCP servers and external integrations.
    """
    __tablename__ = "dms_api_agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    role = Column(String, default="viewer")  # viewer/editor/admin
    is_active = Column(Boolean, default=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    folder_access = relationship("AgentFolderAccess", back_populates="agent", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "token": self.token,
            "role": self.role,
            "is_active": self.is_active,
            "description": self.description,
            "folder_ids": [a.folder_id for a in self.folder_access],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }

    def to_safe_dict(self):
        """Dict without full token (shows only prefix)."""
        d = self.to_dict()
        d["token_preview"] = self.token[:12] + "..." if self.token else ""
        del d["token"]
        return d


class AgentFolderAccess(DmsBase):
    """Maps agents to folders they are allowed to access."""
    __tablename__ = "dms_agent_folder_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("dms_api_agents.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(Integer, ForeignKey("dms_folders.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("ApiAgent", back_populates="folder_access")
    folder = relationship("Folder")

    __table_args__ = (
        UniqueConstraint("agent_id", "folder_id", name="uq_agent_folder"),
    )


# ============================================================
# AuditLog (Operation Audit Trail)
# ============================================================

class AuditLog(DmsBase):
    __tablename__ = "dms_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String, nullable=False)  # create/update/delete/status_change/download/approve/reject/lock/unlock
    target_type = Column(String, nullable=False)  # document/folder/entity/tag
    target_id = Column(Integer, nullable=True)
    target_title = Column(String, nullable=True)
    details = Column(Text, nullable=True)  # JSON
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ============================================================
# SystemSetting (Key-Value Configuration)
# ============================================================

class SystemSetting(DmsBase):
    __tablename__ = "dms_system_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def get_setting(key: str, default: str = None) -> str | None:
    """Get a system setting value by key."""
    if _DmsSessionLocal is None:
        init_dms_db()
    session = _DmsSessionLocal()
    try:
        setting = session.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting else default
    finally:
        session.close()


def set_setting(key: str, value: str, description: str = None):
    """Set a system setting value."""
    if _DmsSessionLocal is None:
        init_dms_db()
    session = _DmsSessionLocal()
    try:
        setting = session.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            setting.value = value
            if description is not None:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            session.add(setting)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================
# ChatHistory (Persisted chat sessions)
# ============================================================

class ChatHistory(DmsBase):
    __tablename__ = "dms_chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    messages_json = Column(Text, default="[]")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def recompute_subtree_paths(session: Session, folder: Folder):
    """Recompute materialized paths for a folder and all descendants."""
    folder.path = folder.compute_path()
    for child in folder.children:
        recompute_subtree_paths(session, child)


# ============================================================
# BidProject (Bid/Procurement Project)
# ============================================================

VALID_BID_TRANSITIONS = {
    "planning": {"active"},
    "active": {"submitted"},
    "submitted": {"won", "lost", "cancelled"},
    "won": set(),
    "lost": set(),
    "cancelled": set(),
}


class BidProject(DmsBase):
    __tablename__ = "dms_bid_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    bid_number = Column(String, nullable=True)
    buyer = Column(String, nullable=True)
    folder_id = Column(Integer, ForeignKey("dms_folders.id"), nullable=True)
    status = Column(String, default="planning")
    budget = Column(String, nullable=True)
    deadline = Column(Date, nullable=True)
    description = Column(String, nullable=True)
    result = Column(String, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    folder = relationship("Folder")
    requirements = relationship("BidRequirement", back_populates="bid_project", cascade="all, delete-orphan")
    team_members = relationship("BidTeamMember", back_populates="bid_project", cascade="all, delete-orphan")

    def can_transition_to(self, new_status: str) -> bool:
        allowed = VALID_BID_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "bid_number": self.bid_number,
            "buyer": self.buyer,
            "folder_id": self.folder_id,
            "status": self.status,
            "budget": self.budget,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "description": self.description,
            "result": self.result,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "folder": {"id": self.folder.id, "name": self.folder.name, "path": self.folder.path} if self.folder else None,
        }


# ============================================================
# BidRequirement (Document Requirement per Bid)
# ============================================================

class BidRequirement(DmsBase):
    __tablename__ = "dms_bid_requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bid_project_id = Column(Integer, ForeignKey("dms_bid_projects.id"), nullable=False)
    doc_type_id = Column(Integer, ForeignKey("dms_doc_types.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_required = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bid_project = relationship("BidProject", back_populates="requirements")
    doc_type = relationship("DocType")
    bid_documents = relationship("BidDocument", back_populates="requirement", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "bid_project_id": self.bid_project_id,
            "doc_type_id": self.doc_type_id,
            "doc_type": {"id": self.doc_type.id, "name": self.doc_type.name, "code": self.doc_type.code} if self.doc_type else None,
            "title": self.title,
            "description": self.description,
            "is_required": self.is_required,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# BidTeamMember (Team Assignment per Bid)
# ============================================================

class BidTeamMember(DmsBase):
    __tablename__ = "dms_bid_team_members"
    __table_args__ = (
        UniqueConstraint("bid_project_id", "entity_id", "role", name="uq_bid_team_member"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bid_project_id = Column(Integer, ForeignKey("dms_bid_projects.id"), nullable=False)
    entity_id = Column(Integer, ForeignKey("dms_entities.id"), nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bid_project = relationship("BidProject", back_populates="team_members")
    entity = relationship("Entity")

    def to_dict(self):
        return {
            "id": self.id,
            "bid_project_id": self.bid_project_id,
            "entity_id": self.entity_id,
            "entity_name": self.entity.name if self.entity else None,
            "entity_type": self.entity.entity_type if self.entity else None,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# BidDocument (Requirement-Document Link)
# ============================================================

class BidDocument(DmsBase):
    __tablename__ = "dms_bid_documents"
    __table_args__ = (
        UniqueConstraint("bid_requirement_id", "document_id", name="uq_bid_req_doc"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bid_requirement_id = Column(Integer, ForeignKey("dms_bid_requirements.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("dms_documents.id"), nullable=False)
    status = Column(String, default="linked")  # linked/verified
    linked_by = Column(Integer, nullable=True)
    linked_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(String, nullable=True)

    requirement = relationship("BidRequirement", back_populates="bid_documents")
    document = relationship("DmsDocument")

    def to_dict(self):
        return {
            "id": self.id,
            "bid_requirement_id": self.bid_requirement_id,
            "document_id": self.document_id,
            "document_title": self.document.title if self.document else None,
            "status": self.status,
            "linked_by": self.linked_by,
            "linked_at": self.linked_at.isoformat() if self.linked_at else None,
            "notes": self.notes,
        }

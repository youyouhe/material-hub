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

        if "dms_entities" in tables:
            result = conn.execute(text("PRAGMA table_info(dms_entities)"))
            columns = [row[1] for row in result]
            if "credit_code" not in columns:
                conn.execute(text("ALTER TABLE dms_entities ADD COLUMN credit_code TEXT"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_entities_credit_code ON dms_entities(credit_code)"))
                conn.commit()
            if "company_id_legacy" not in columns:
                conn.execute(text("ALTER TABLE dms_entities ADD COLUMN company_id_legacy INTEGER"))
                conn.commit()

        # Ensure entity relation indexes exist
        if "dms_entity_relations" in tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_entity_rel_from ON dms_entity_relations(from_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_entity_rel_to ON dms_entity_relations(to_id)"))
            conn.commit()

        # Migration: add title + created_at to dms_chat_history
        if "dms_chat_history" in tables:
            result = conn.execute(text("PRAGMA table_info(dms_chat_history)"))
            columns = [row[1] for row in result]
            if "title" not in columns:
                conn.execute(text("ALTER TABLE dms_chat_history ADD COLUMN title TEXT"))
                conn.commit()
            if "created_at" not in columns:
                conn.execute(text("ALTER TABLE dms_chat_history ADD COLUMN created_at TIMESTAMP"))
                conn.commit()

    # Initialize FTS5 search index table
    from dms_search import init_fts_table
    init_fts_table()

    # Seed default admin user + system roles
    _seed_dms_default_admin()
    _seed_system_roles()


def _seed_dms_default_admin():
    """Create default admin user in dms_users if table is empty."""
    import bcrypt
    import os as _os
    with get_dms_session() as session:
        if session.query(DmsUser).count() == 0:
            default_username = _os.getenv("AUTH_DEFAULT_USERNAME", "admin")
            default_password = _os.getenv("AUTH_DEFAULT_PASSWORD", "admin123")
            password_hash = bcrypt.hashpw(
                default_password.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')
            session.add(DmsUser(
                username=default_username,
                password_hash=password_hash,
                role="admin",
            ))
            logger.info("Seeded default DMS admin user: %s", default_username)


def _seed_system_roles():
    """Create system roles if they don't exist, and assign default folder permissions."""
    SYSTEM_ROLES = [
        {"name": "admin", "description": "系统管理员，全局访问", "is_system": True},
        {"name": "editor", "description": "编辑者，可读写分配的文件夹", "is_system": True},
        {"name": "viewer", "description": "只读者，可查看所有文件夹", "is_system": True},
    ]

    with get_dms_session() as session:
        existing = {r.name for r in session.query(DmsRole).all()}
        new_roles = []

        for rdef in SYSTEM_ROLES:
            if rdef["name"] not in existing:
                role = DmsRole(**rdef)
                session.add(role)
                session.flush()
                new_roles.append(role)
                logger.info("Created system role: %s", rdef["name"])

        if not new_roles:
            return

        # Assign default folder permissions for non-admin roles
        folders = session.query(Folder).all()
        for role in new_roles:
            if role.name == "admin":
                continue  # Admin has implicit full access
            perm = "write" if role.name == "editor" else "read"
            for folder in folders:
                session.add(DmsRoleFolderPermission(
                    role_id=role.id, folder_id=folder.id, permission=perm
                ))
        logger.info("Seeded default folder permissions for %d role(s) across %d folders",
                     len(new_roles), len(folders))


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
# DmsRole (RBAC role definition)
# ============================================================

class DmsRole(DmsBase):
    """Named role with configurable folder-level permissions."""
    __tablename__ = "dms_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    is_system = Column(Boolean, default=False)  # system roles cannot be deleted
    created_at = Column(DateTime, default=datetime.utcnow)

    folder_permissions = relationship("DmsRoleFolderPermission", back_populates="role",
                                      cascade="all, delete-orphan")
    user_assignments = relationship("DmsUserRole", back_populates="role",
                                    cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# DmsRoleFolderPermission (role → folder access level)
# ============================================================

class DmsRoleFolderPermission(DmsBase):
    """Grants a role specific permission level on a folder."""
    __tablename__ = "dms_role_folder_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "folder_id", name="uq_role_folder_perm"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("dms_roles.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(Integer, ForeignKey("dms_folders.id", ondelete="CASCADE"), nullable=False)
    permission = Column(String, nullable=False, default="read")  # read | write | admin
    created_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("DmsRole", back_populates="folder_permissions")
    folder = relationship("Folder")

    def to_dict(self):
        return {
            "id": self.id,
            "role_id": self.role_id,
            "folder_id": self.folder_id,
            "folder_name": self.folder.name if self.folder else None,
            "folder_path": self.folder.path if self.folder else None,
            "permission": self.permission,
        }


# ============================================================
# DmsUserRole (user → role assignment)
# ============================================================

class DmsUserRole(DmsBase):
    """Assigns a user to a role."""
    __tablename__ = "dms_user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("dms_users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("dms_roles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("DmsUser", backref="role_assignments")
    role = relationship("DmsRole", back_populates="user_assignments")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "role_id": self.role_id,
            "role_name": self.role.name if self.role else None,
        }


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
# DmsUser (Authentication)
# ============================================================

class DmsUser(DmsBase):
    __tablename__ = "dms_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="editor")  # admin/editor/viewer
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    legacy_user_id = Column(Integer, nullable=True)  # 旧 users.id 对应关系

    sessions = relationship("DmsSession", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role or "editor",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "legacy_user_id": self.legacy_user_id,
        }


# ============================================================
# DmsSession (Authentication Token)
# ============================================================

class DmsSession(DmsBase):
    __tablename__ = "dms_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("dms_users.id"), nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("DmsUser", back_populates="sessions")


# ============================================================
# EntityRelation (Relationship between Entities)
# ============================================================

class EntityRelation(DmsBase):
    """Relationships between entities (e.g., employed_by, subsidiary_of)."""
    __tablename__ = "dms_entity_relations"
    __table_args__ = (
        UniqueConstraint("from_id", "to_id", "relation", name="uq_entity_rel"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_id = Column(Integer, ForeignKey("dms_entities.id", ondelete="CASCADE"), nullable=False)
    to_id = Column(Integer, ForeignKey("dms_entities.id", ondelete="CASCADE"), nullable=False)
    relation = Column(String, nullable=False)  # employed_by / subsidiary_of / parent_of
    attributes = Column(Text, nullable=True)   # JSON extra info
    created_at = Column(DateTime, default=datetime.utcnow)

    from_entity = relationship("Entity", foreign_keys=[from_id], backref="outgoing_relations")
    to_entity = relationship("Entity", foreign_keys=[to_id], backref="incoming_relations")

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
            "from_id": self.from_id,
            "to_id": self.to_id,
            "relation": self.relation,
            "from_name": self.from_entity.name if self.from_entity else None,
            "to_name": self.to_entity.name if self.to_entity else None,
            "attributes": attrs,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# ============================================================
# McpToken (SSE access token bound to an agent/role)
# ============================================================

class DmsMcpToken(DmsBase):
    """MCP SSE access token linked to an ApiAgent for role-based access."""
    __tablename__ = "dms_mcp_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # display name
    sse_token = Column(String, nullable=False, unique=True, index=True)  # mcp-sse-xxx
    agent_id = Column(Integer, ForeignKey("dms_api_agents.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("ApiAgent", backref="mcp_tokens")

    def to_dict(self, show_token: bool = False):
        return {
            "id": self.id,
            "name": self.name,
            "sse_token": self.sse_token if show_token else (self.sse_token[:20] + "..." if self.sse_token else ""),
            "agent_id": self.agent_id,
            "agent_name": self.agent.name if self.agent else None,
            "agent_role": self.agent.role if self.agent else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# ChatHistory (Persisted chat sessions)
# ============================================================

class ChatHistory(DmsBase):
    __tablename__ = "dms_chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=True)  # session name, auto-generated from first message
    messages_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        import json
        msgs = []
        if self.messages_json:
            try:
                msgs = json.loads(self.messages_json)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title or f"对话 {self.id}",
            "message_count": len(msgs),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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

"""
Knowledge Base SQLAlchemy Models (PostgreSQL + pgvector).

Mirrors SAG's data model adapted for MaterialHub:
  kb_chunks         — document chunks with embedding vectors
  kb_entities       — entity mirror from dms_entities with embeddings
  kb_entity_relations — entity relationship mirror
  kb_events         — extracted events (title, description, date, type)
  kb_event_entities — event <-> entity junction
  kb_chunk_events   — chunk <-> event junction
  kb_folders        — folder denormalization for RBAC filtering
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Date, DateTime,
    ForeignKey, Index, Float, JSON,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from kb_database import KBBase


# ============================================================
# kb_chunks — Document chunks with embedding vectors
# ============================================================

class KbChunk(KBBase):
    __tablename__ = "kb_chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, nullable=False, index=True, comment="FK to SQLite dms_documents.id")
    chunk_index = Column(Integer, nullable=False, comment="0-based chunk order within document")
    content = Column(Text, nullable=False)
    heading_path = Column(String(512), nullable=True, comment="Section heading hierarchy if detected")
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(Vector(1024), nullable=True, comment="Content embedding (1024-dim)")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_kb_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "heading_path": self.heading_path,
            "token_count": self.token_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# kb_entities — Entity mirror with embeddings
# ============================================================

class KbEntity(KBBase):
    __tablename__ = "kb_entities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dms_entity_id = Column(Integer, nullable=False, unique=True, index=True, comment="FK to SQLite dms_entities.id")
    name = Column(String(512), nullable=False)
    entity_type = Column(String(32), nullable=False, comment="org | person")
    description = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=True, comment="Name+description embedding")
    attributes = Column(JSON, nullable=True, comment="Mirrored from dms_entities.attributes")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_kb_entities_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_kb_entities_type", "entity_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "dms_entity_id": self.dms_entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# kb_entity_relations — Entity relationship mirror
# ============================================================

class KbEntityRelation(KBBase):
    __tablename__ = "kb_entity_relations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    from_entity_id = Column(BigInteger, ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False)
    to_entity_id = Column(BigInteger, ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False)
    relation = Column(String(64), nullable=False, comment="employed_by | subsidiary_of | parent_of")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_kb_er_from", "from_entity_id"),
        Index("ix_kb_er_to", "to_entity_id"),
        Index("ix_kb_er_pair", "from_entity_id", "to_entity_id", "relation", unique=True),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "from_entity_id": self.from_entity_id,
            "to_entity_id": self.to_entity_id,
            "relation": self.relation,
        }


# ============================================================
# kb_events — Extracted events
# ============================================================

class KbEvent(KBBase):
    __tablename__ = "kb_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, nullable=False, index=True, comment="FK to SQLite dms_documents.id")
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(Date, nullable=True, index=True)
    event_type = Column(String(64), nullable=True, comment="e.g. signing, expiration, certification, employment")
    embedding = Column(Vector(1024), nullable=True, comment="Title+description embedding")
    source_chunk_ids = Column(ARRAY(Integer), nullable=True, comment="KB chunk IDs that produced this event")
    attributes = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_kb_events_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "title": self.title,
            "description": self.description,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "event_type": self.event_type,
            "source_chunk_ids": self.source_chunk_ids,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# kb_event_entities — Event <-> Entity junction
# ============================================================

class KbEventEntity(KBBase):
    __tablename__ = "kb_event_entities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(BigInteger, ForeignKey("kb_events.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(BigInteger, ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(64), nullable=True, comment="Entity role in event: participant, issuer, subject, etc.")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_kb_ee_pair", "event_id", "entity_id", unique=True),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "role": self.role,
        }


# ============================================================
# kb_chunk_events — Chunk <-> Event junction
# ============================================================

class KbChunkEvent(KBBase):
    __tablename__ = "kb_chunk_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chunk_id = Column(BigInteger, ForeignKey("kb_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(BigInteger, ForeignKey("kb_events.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_kb_ce_pair", "chunk_id", "event_id", unique=True),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "chunk_id": self.chunk_id,
            "event_id": self.event_id,
        }


# ============================================================
# kb_folders — Folder denormalization for RBAC in vector search
# ============================================================

class KbFolder(KBBase):
    __tablename__ = "kb_folders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dms_folder_id = Column(Integer, nullable=False, unique=True, index=True, comment="FK to SQLite dms_folders.id")
    name = Column(String(256), nullable=False)
    path = Column(String(1024), nullable=False, index=True, comment="Materialized path like /公司资质/营业执照/")
    parent_id = Column(Integer, nullable=True, comment="FK to SQLite dms_folders.parent_id")
    updated_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "dms_folder_id": self.dms_folder_id,
            "name": self.name,
            "path": self.path,
            "parent_id": self.parent_id,
        }

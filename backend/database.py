"""
Database models and session management for MaterialHub.
SQLite + SQLAlchemy for metadata; images stored on filesystem.
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Date, ForeignKey, event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

logger = logging.getLogger("materialhub.database")

DEFAULT_DB_PATH = "data/materials.db"

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    section_count = Column(Integer, default=0)
    image_count = Column(Integer, default=0)

    materials = relationship(
        "Material", back_populates="document", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "upload_time": self.upload_time.isoformat() if self.upload_time else None,
            "section_count": self.section_count,
            "image_count": self.image_count,
        }


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    section = Column(String, default="")
    title = Column(String, nullable=False)
    heading_level = Column(Integer, default=1)
    image_filename = Column(String, nullable=False)
    image_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    expiry_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="materials")

    def to_dict(self):
        today = date.today()
        expired = self.expiry_date < today if self.expiry_date else None
        return {
            "id": self.id,
            "document_id": self.document_id,
            "source_filename": self.document.filename if self.document else None,
            "section": self.section,
            "title": self.title,
            "heading_level": self.heading_level,
            "image_filename": self.image_filename,
            "image_url": f"/api/files/{self.image_filename}",
            "file_size": self.file_size,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "is_expired": expired,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# --- Engine & Session ---

_engine = None
_SessionLocal = None


def get_db_path() -> str:
    return os.getenv("DB_PATH", DEFAULT_DB_PATH)


def init_db():
    global _engine, _SessionLocal
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{db_path}", echo=False)

    # Enable WAL mode for better concurrent reads
    @event.listens_for(_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)
    logger.info("Database initialized at %s", db_path)


@contextmanager
def get_session():
    if _SessionLocal is None:
        init_db()
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

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


class Company(Base):
    """公司主体信息"""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # 公司名称
    legal_person = Column(String)  # 法定代表人
    credit_code = Column(String)  # 统一社会信用代码
    address = Column(String)  # 地址
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    documents = relationship("Document", back_populates="company")
    materials = relationship("Material", back_populates="company")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "legal_person": self.legal_person,
            "credit_code": self.credit_code,
            "address": self.address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Person(Base):
    """人员信息"""
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # 姓名
    id_number = Column(String)  # 身份证号
    education = Column(String)  # 学历
    position = Column(String)  # 职位
    company_id = Column(Integer, ForeignKey("companies.id"))  # 所属公司
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    company = relationship("Company")
    materials = relationship("Material", back_populates="person")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "id_number": self.id_number,
            "education": self.education,
            "position": self.position,
            "company_id": self.company_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    docx_path = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    upload_time = Column(DateTime, default=datetime.utcnow)
    section_count = Column(Integer, default=0)
    image_count = Column(Integer, default=0)

    materials = relationship(
        "Material", back_populates="document", cascade="all, delete-orphan"
    )
    company = relationship("Company", back_populates="documents")

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "docx_path": self.docx_path,
            "company_id": self.company_id,
            "company_name": self.company.name if self.company else None,
            "upload_time": self.upload_time.isoformat() if self.upload_time else None,
            "section_count": self.section_count,
            "image_count": self.image_count,
        }


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    section = Column(String, default="")
    title = Column(String, nullable=False)
    heading_level = Column(Integer, default=1)
    image_filename = Column(String, nullable=False)
    image_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    expiry_date = Column(Date, nullable=True)
    ocr_text = Column(String, nullable=True)  # OCR识别的文本
    material_type = Column(String, nullable=True)  # 材料类型：license, id_card, certificate等
    extracted_json = Column(String, nullable=True)  # LLM提取的结构化JSON数据
    ocr_status = Column(String, nullable=True)  # OCR状态：pending/processing/completed/failed
    ocr_error = Column(String, nullable=True)  # OCR错误信息
    ocr_processed_at = Column(DateTime, nullable=True)  # OCR处理时间
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="materials")
    company = relationship("Company", back_populates="materials")
    person = relationship("Person", back_populates="materials")

    def to_dict(self):
        today = date.today()
        expired = self.expiry_date < today if self.expiry_date else None

        # Parse extracted_json if exists
        extracted_data = None
        if self.extracted_json:
            try:
                import json
                extracted_data = json.loads(self.extracted_json)
            except:
                pass

        return {
            "id": self.id,
            "document_id": self.document_id,
            "company_id": self.company_id,
            "person_id": self.person_id,
            "source_filename": self.document.filename if self.document else None,
            "section": self.section,
            "title": self.title,
            "heading_level": self.heading_level,
            "image_filename": self.image_filename,
            "image_url": f"/api/files/{self.image_filename}",
            "file_size": self.file_size,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "is_expired": expired,
            "material_type": self.material_type,
            "ocr_text": self.ocr_text,
            "extracted_data": extracted_data,
            "ocr_status": self.ocr_status,
            "ocr_error": self.ocr_error,
            "ocr_processed_at": self.ocr_processed_at.isoformat() if self.ocr_processed_at else None,
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

    # Run migrations before creating tables
    _run_migrations(_engine)

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)
    logger.info("Database initialized at %s", db_path)


def _run_migrations(engine):
    """Run database migrations."""
    text = __import__('sqlalchemy').text
    inspect = __import__('sqlalchemy').inspect

    with engine.connect() as conn:
        tables = inspect(engine).get_table_names()

        # Migration 1: Add docx_path column to documents table
        try:
            if 'documents' in tables:
                result = conn.execute(text("PRAGMA table_info(documents)"))
                columns = [row[1] for row in result]

                if 'docx_path' not in columns:
                    logger.info("Migration: adding docx_path to documents")
                    conn.execute(text("ALTER TABLE documents ADD COLUMN docx_path TEXT"))
                    conn.commit()
        except Exception as e:
            logger.warning("Migration docx_path error: %s", e)

        # Migration 2: Add company_id to documents table
        try:
            if 'documents' in tables:
                result = conn.execute(text("PRAGMA table_info(documents)"))
                columns = [row[1] for row in result]

                if 'company_id' not in columns:
                    logger.info("Migration: adding company_id to documents")
                    conn.execute(text("ALTER TABLE documents ADD COLUMN company_id INTEGER"))
                    conn.commit()
        except Exception as e:
            logger.warning("Migration company_id error: %s", e)

        # Migration 3: Add new columns to materials table
        try:
            if 'materials' in tables:
                result = conn.execute(text("PRAGMA table_info(materials)"))
                columns = [row[1] for row in result]

                if 'company_id' not in columns:
                    logger.info("Migration: adding company_id to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN company_id INTEGER"))
                    conn.commit()

                if 'person_id' not in columns:
                    logger.info("Migration: adding person_id to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN person_id INTEGER"))
                    conn.commit()

                if 'ocr_text' not in columns:
                    logger.info("Migration: adding ocr_text to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN ocr_text TEXT"))
                    conn.commit()

                if 'material_type' not in columns:
                    logger.info("Migration: adding material_type to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN material_type TEXT"))
                    conn.commit()

                if 'extracted_json' not in columns:
                    logger.info("Migration: adding extracted_json to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN extracted_json TEXT"))
                    conn.commit()

                if 'ocr_status' not in columns:
                    logger.info("Migration: adding ocr_status to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN ocr_status TEXT"))
                    conn.commit()

                if 'ocr_error' not in columns:
                    logger.info("Migration: adding ocr_error to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN ocr_error TEXT"))
                    conn.commit()

                if 'ocr_processed_at' not in columns:
                    logger.info("Migration: adding ocr_processed_at to materials")
                    conn.execute(text("ALTER TABLE materials ADD COLUMN ocr_processed_at TIMESTAMP"))
                    conn.commit()
        except Exception as e:
            logger.warning("Migration materials error: %s", e)


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

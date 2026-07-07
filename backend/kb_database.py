"""
Knowledge Base PostgreSQL Connection Manager.

Provides a SQLAlchemy engine + session factory for the KB database,
separate from the main SQLite database. Used for vector search,
knowledge graph, and multi-hop reasoning (Phase 0-3).
"""

import os
import logging
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("materialhub.kb_database")

# PostgreSQL connection settings
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DATABASE = os.getenv("PG_DATABASE", "materialhub_kb")
PG_USER = os.getenv("PG_USER", "materialhub")
PG_PASSWORD = os.getenv("PG_PASSWORD", "materialhub")

# Build connection URL with special character handling
_encoded_password = quote_plus(PG_PASSWORD)
DATABASE_URL = os.getenv(
    "KB_DATABASE_URL",
    f"postgresql://{PG_USER}:{_encoded_password}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}",
)

# SQLAlchemy engine (lazy init)
_engine = None
_SessionLocal = None

# Declarative base for all KB models
KBBase = declarative_base()


def _build_engine():
    """Create the PostgreSQL engine with connection pooling."""
    return create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # verify connections before use
        echo=False,
    )


def get_engine():
    """Get or create the PostgreSQL engine (singleton)."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
        logger.info("PostgreSQL engine created for KB database")
    return _engine


def get_session_local():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def get_kb_session():
    """Context manager yielding a KB database session."""
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_pgvector_extension():
    """Create pgvector extension if not exists."""
    from sqlalchemy import text
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    logger.info("pgvector extension ensured")


def init_kb_db():
    """Initialize KB database: create tables and indexes.

    Called from main.py startup. Safe to call multiple times
    (CREATE TABLE IF NOT EXISTS).

    Does NOT fail if PostgreSQL is unreachable — logs a warning
    so the rest of MaterialHub still works with FTS5 search.
    """
    try:
        from sqlalchemy import text
        engine = get_engine()
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        ensure_pgvector_extension()

        # Create all KB tables
        from kb_models import (  # noqa: F401 - import triggers model registration
            KbChunk, KbEntity, KbEntityRelation, KbEvent,
            KbEventEntity, KbChunkEvent, KbFolder,
        )
        KBBase.metadata.create_all(bind=engine)

        logger.info("KB database initialized successfully")
    except Exception as e:
        logger.warning(
            "KB database unavailable — knowledge base features disabled. "
            "FTS5 search remains functional. Error: %s", e
        )

"""
Operational data store (SQLAlchemy).

Polyglot persistence by design: **DuckDB** stays the analytical engine for the
transaction reference data (OLAP), while this SQLAlchemy store holds the
*operational* app data — users and case assignments — that a real product needs.
It is **Postgres-ready** (set `DATABASE_URL`, e.g. a free Neon/Supabase instance)
and falls back to a local **SQLite** file so the whole thing still runs at $0.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import PROCESSED_DIR, settings


def _database_url() -> str:
    if settings.database_url:
        url = settings.database_url
        # Neon/Heroku hand out "postgres://"; SQLAlchemy wants "postgresql://".
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    return f"sqlite:///{PROCESSED_DIR / 'operational.sqlite'}"


DATABASE_URL = _database_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_models() -> None:
    from app import models  # noqa: F401 - ensure models are registered

    Base.metadata.create_all(bind=engine)


def backend_info() -> dict:
    return {"operational_db": "postgresql" if not _is_sqlite else "sqlite"}

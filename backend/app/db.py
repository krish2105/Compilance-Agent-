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
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Add columns introduced after a table was first created (SQLite dev DBs that
    persist across runs). Postgres/prod uses an ephemeral fresh schema. Best-effort."""
    if not _is_sqlite:
        return
    from sqlalchemy import inspect, text

    try:
        insp = inspect(engine)
        if "users" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("users")}
            with engine.begin() as con:
                if "tenant_id" not in cols:
                    con.execute(text("ALTER TABLE users ADD COLUMN tenant_id INTEGER DEFAULT 1"))
                if "token_version" not in cols:
                    con.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0"))
        if "tenants" in insp.get_table_names():
            tcols = {c["name"] for c in insp.get_columns("tenants")}
            if "plan" not in tcols:
                with engine.begin() as con:
                    con.execute(text("ALTER TABLE tenants ADD COLUMN plan VARCHAR(16) DEFAULT 'free'"))
    except Exception:  # noqa: BLE001 - never block startup on a migration
        pass


def backend_info() -> dict:
    return {
        "operational_db": "postgresql" if not _is_sqlite else "sqlite",
        # Postgres persists across restarts; the local SQLite file is ephemeral on
        # a free-tier container (rebuilt on each deploy).
        "durable": not _is_sqlite,
    }

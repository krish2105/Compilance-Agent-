"""
Central configuration for ComplianceAgent.

All settings are sourced from environment variables (loaded from a local `.env`
file in development). Nothing sensitive is ever hardcoded here.

The LLM provider is selected via a single environment variable so the underlying
model provider can be swapped with a one-line config change, per the project's
$0/month, provider-agnostic design goal.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve important paths relative to the backend package regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Load .env early so os.environ is populated before Settings is built.
load_dotenv(BACKEND_DIR / ".env")


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Read once at startup and cached (see `get_settings`).
    """

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "ComplianceAgent"
    environment: str = Field(default="development")

    # ---- Auth ----
    # Simple shared-secret API key that protects the backend routes.
    # In development the default key lets the bundled frontend work out of the box.
    backend_api_key: str = Field(default="dev-local-key", alias="BACKEND_API_KEY")

    # ---- LLM provider selection ----
    # One of: "offline" | "gemini" | "groq".
    # "offline" is a deterministic, zero-cost, no-network provider so the whole
    # system runs end-to-end with no API keys. "gemini" is the intended primary
    # provider; "groq" is the failover lane.
    llm_provider: str = Field(default="offline", alias="LLM_PROVIDER")
    # When True, a rate-limit / failure on the primary provider automatically
    # falls back to Groq, and finally to the deterministic offline provider.
    llm_enable_fallback: bool = Field(default=True, alias="LLM_ENABLE_FALLBACK")

    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")

    # ---- Data / storage ----
    # Vector store backend for the Regulatory-Context RAG: "memory" (zero-dependency,
    # default — great for $0/512MB hosting & CI) or "chroma" (ChromaDB; requires
    # requirements-full.txt).
    vector_backend: str = Field(default="memory", alias="VECTOR_BACKEND")

    duckdb_path: str = Field(
        default=str(PROCESSED_DIR / "compliance.duckdb"), alias="DUCKDB_PATH"
    )
    chroma_path: str = Field(
        default=str(PROCESSED_DIR / "chroma"), alias="CHROMA_PATH"
    )
    audit_db_path: str = Field(
        default=str(PROCESSED_DIR / "audit_log.sqlite"), alias="AUDIT_DB_PATH"
    )

    # ---- Rate limiting (per client key, sliding window) ----
    rate_limit_requests: int = Field(default=30, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")

    # ---- CORS ----
    cors_origins: str = Field(
        default=(
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:5175,http://127.0.0.1:5175"
        ),
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Convenience singleton used by modules that don't need DI.
settings = get_settings()

# Make sure processed dir exists for DuckDB / Chroma / SQLite outputs.
os.makedirs(PROCESSED_DIR, exist_ok=True)

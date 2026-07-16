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
    # Simple shared-secret API key that protects the backend routes (demo/legacy lane).
    # In development the default key lets the bundled frontend work out of the box.
    backend_api_key: str = Field(default="dev-local-key", alias="BACKEND_API_KEY")
    # JWT signing secret + token lifetime for the user-auth lane (RBAC).
    jwt_secret: str = Field(default="dev-jwt-secret-change-me", alias="JWT_SECRET")
    jwt_expire_hours: int = Field(default=12, alias="JWT_EXPIRE_HOURS")
    # Operational store: Postgres via DATABASE_URL, else a local SQLite file ($0).
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    # Cache: Redis via REDIS_URL (e.g. Upstash free), else an in-process TTL cache.
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    cache_ttl_seconds: int = Field(default=300, alias="CACHE_TTL_SECONDS")

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
    # Cheaper tier used by the model router for lightweight/classification tasks.
    # Defaults to gemini-2.5-flash (universally available); set GEMINI_MODEL_LIGHT to a
    # cheaper model like gemini-2.0-flash-lite if your key/project has quota for it.
    gemini_model_light: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL_LIGHT")

    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    groq_model_light: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL_LIGHT")

    # ---- Hallucination guardrail (Verifier NLI entailment via HF Inference API) ----
    # A free-tier HuggingFace token enables an independent natural-language-inference
    # check: every substantive narrative statement must be *entailed* by the evidence.
    # Absent a token (e.g. CI), the check no-ops and the deterministic guardrails stand.
    huggingface_token: Optional[str] = Field(default=None, alias="HUGGINGFACE_TOKEN")
    verifier_entailment: bool = Field(default=True, alias="VERIFIER_ENTAILMENT")
    hf_nli_model: str = Field(
        default="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", alias="HF_NLI_MODEL")
    # Entailment probability below this = "not supported by evidence".
    entailment_threshold: float = Field(default=0.5, alias="ENTAILMENT_THRESHOLD")
    # HF serverless cold-starts can take 20-30s on first use; we send X-Wait-For-Model
    # so the API blocks until the model is loaded rather than erroring.
    entailment_timeout: float = Field(default=45.0, alias="ENTAILMENT_TIMEOUT")
    # Cap HF calls per case (free-tier rate limits): number of statements checked.
    entailment_max_checks: int = Field(default=8, alias="ENTAILMENT_MAX_CHECKS")

    # ---- Observability (Langfuse — optional; tracing is a no-op if unset) ----
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # ---- Data / storage ----
    # Vector store backend for the Regulatory-Context RAG: "memory" (zero-dependency,
    # default — great for $0/512MB hosting & CI) or "chroma" (ChromaDB; requires
    # requirements-full.txt).
    vector_backend: str = Field(default="memory", alias="VECTOR_BACKEND")

    # ---- Advanced RAG ----
    # Embeddings: "hashing" (offline, $0, default) or "gemini" (neural, needs key).
    embedding_backend: str = Field(default="ngram", alias="EMBEDDING_BACKEND")
    # Retrieval: "hybrid" (BM25+dense RRF, default) | "dense" | "bm25".
    retrieval_mode: str = Field(default="hybrid", alias="RETRIEVAL_MODE")
    # Reranker: "lexical" (deterministic, default) | "llm" (Gemini) | "none".
    reranker: str = Field(default="lexical", alias="RERANKER")

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

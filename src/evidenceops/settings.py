"""Typed local configuration for EvidenceOps."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Local-first settings with CPU-safe defaults and environment overrides."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "evidenceops_chunks"
    qdrant_timeout_seconds: int = Field(default=10, gt=0)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_timeout_seconds: int = Field(default=60, gt=0)
    ollama_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = Field(default=384, gt=0)
    embedding_distance: str = "Cosine"
    flashrank_model: str = "ms-marco-TinyBERT-L-2-v2"
    rrf_k: int = Field(default=60, gt=0)
    top_k_sparse: int = Field(default=20, gt=0)
    top_k_dense: int = Field(default=20, gt=0)
    top_k_hybrid: int = Field(default=20, gt=0)
    top_k_context: int = Field(default=6, gt=0)
    max_iterations: int = Field(default=3, ge=1, le=3)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    max_context_chars: int = Field(default=24000, gt=0)
    sufficiency_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    abstain_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    otel_service_name: str = "evidenceops-api"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    simulated_cloud_input_cost_usd_per_1k: float = Field(default=0.0, ge=0.0)
    simulated_cloud_output_cost_usd_per_1k: float = Field(default=0.0, ge=0.0)
    raw_data_dir: Path = Path("data/raw")
    max_source_bytes: int = Field(default=10_000_000, gt=0)
    supported_source_extensions: str = ".md,.markdown,.txt,.html,.htm"
    chunk_target_words: int = Field(default=500, ge=350, le=600)
    chunk_max_words: int = Field(default=600, ge=350, le=600)
    chunk_overlap_words: int = Field(default=60, ge=50, le=80)
    manifest_dir: Path = Path("data/manifests")
    processed_data_dir: Path = Path("data/processed")
    manifest_schema_version: str = "1.0"

    @field_validator("qdrant_url", "ollama_base_url", "otel_exporter_otlp_endpoint")
    @classmethod
    def local_service_url(cls, value: str) -> str:
        hostname = urlparse(value).hostname
        if hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("local service URLs must use localhost or 127.0.0.1")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-local settings instance."""
    return Settings()

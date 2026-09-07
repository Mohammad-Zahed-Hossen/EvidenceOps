"""LiteBridge-owned immutable public domain contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExecutionProfile(StrEnum):
    """Supported operating profiles for LiteBridge."""

    LOCAL_ONLY = "local_only"
    HYBRID = "hybrid"
    HOSTED = "hosted"


class SourceKind(StrEnum):
    """Supported evidence source categories in LiteBridge Phase L1."""

    LOCAL_DOCUMENT = "local_document"


class StopReason(StrEnum):
    """Explicit, typed reasons for concluding context preparation."""

    SUCCESS = "success"
    NO_EVIDENCE = "no_evidence"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    INVALID_QUERY = "invalid_query"
    RETRIEVAL_FAILED = "retrieval_failed"


class RetrievalPolicy(BaseModel):
    """Caller constraints for bounded local retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_ONLY
    mode: Literal["sparse", "dense", "hybrid"] = "hybrid"
    max_evidence_items: int = Field(default=6, ge=1, le=6)
    max_context_chars: int = Field(default=24000, ge=100, le=24000)
    max_estimated_tokens: int = Field(default=6000, ge=25, le=6000)


class EvidenceRecord(BaseModel):
    """Immutable, citation-safe record of a single piece of retrieved evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    citation_id: str = Field(min_length=1)
    source_kind: SourceKind = SourceKind.LOCAL_DOCUMENT
    document_id: str = Field(min_length=1)
    chunk_id: str | None = None
    title: str = ""
    section: str = ""
    source_label: str = ""
    excerpt: str = Field(min_length=1)
    retrieval_route: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = 0.0
    source_version: str | None = None
    metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)


class ContextPackage(BaseModel):
    """Immutable, generator-independent context package produced by LiteBridge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(min_length=1)
    query_hash: str = Field(min_length=1)
    query_length: int = Field(ge=0)
    normalized_query: str = Field(min_length=1)
    execution_profile: ExecutionProfile
    effective_policy: RetrievalPolicy
    evidence: tuple[EvidenceRecord, ...] = Field(default_factory=tuple)
    context_text: str = ""
    max_context_chars: int = Field(ge=100)
    max_estimated_tokens: int = Field(ge=25)
    context_chars: int = Field(default=0, ge=0)
    estimated_tokens: int = Field(default=0, ge=0)
    retrieval_calls: int = Field(default=0, ge=0)
    retrieval_route: str = Field(min_length=1)
    timings_ms: tuple[tuple[str, float], ...] = Field(default_factory=tuple)
    stop_reason: StopReason
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    reproducibility: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

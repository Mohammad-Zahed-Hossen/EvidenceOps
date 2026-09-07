"""LiteBridge-owned immutable public domain contracts."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evidenceops.bridge.errors import LiteBridgeValidationError


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


class PrivacyClassification(StrEnum):
    """Supported privacy classification levels in LiteBridge Phase L2."""

    PRIVATE = "private"


class SourceFreshness(StrEnum):
    """Supported data freshness classifications in LiteBridge Phase L2."""

    SNAPSHOT = "snapshot"


SLUG_REGEX = re.compile(r"^[a-z0-9_-]+$")


class SourceDescriptor(BaseModel):
    """Immutable, LiteBridge-owned public description of one registered source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    display_name: str
    source_kind: SourceKind
    adapter_id: str
    enabled: bool
    privacy_classification: PrivacyClassification
    freshness: SourceFreshness
    citation_required: bool
    max_response_chars: int
    timeout_ms: int
    max_retries: int
    source_version: str | None = None

    @field_validator("source_id")
    @classmethod
    def _validate_source_id(cls, v: str) -> str:
        if not isinstance(v, str) or not SLUG_REGEX.match(v):
            raise ValueError(f"source_id must be a valid slug (^[a-z0-9_-]+$), got '{v}'")
        return v

    @field_validator("adapter_id")
    @classmethod
    def _validate_adapter_id(cls, v: str) -> str:
        if not isinstance(v, str) or not SLUG_REGEX.match(v):
            raise ValueError(f"adapter_id must be a valid slug (^[a-z0-9_-]+$), got '{v}'")
        return v

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("display_name must be nonblank after trimming")
        return v.strip()

    @field_validator("source_kind")
    @classmethod
    def _validate_source_kind(cls, v: SourceKind) -> SourceKind:
        if v != SourceKind.LOCAL_DOCUMENT:
            raise ValueError(
                f"source_kind must be '{SourceKind.LOCAL_DOCUMENT.value}' in Phase L2, got '{v}'"
            )
        return v

    @field_validator("privacy_classification")
    @classmethod
    def _validate_privacy(cls, v: PrivacyClassification) -> PrivacyClassification:
        if v != PrivacyClassification.PRIVATE:
            val = PrivacyClassification.PRIVATE.value
            raise ValueError(f"privacy_classification must be '{val}' in Phase L2")
        return v

    @field_validator("freshness")
    @classmethod
    def _validate_freshness(cls, v: SourceFreshness) -> SourceFreshness:
        if v != SourceFreshness.SNAPSHOT:
            raise ValueError(f"freshness must be '{SourceFreshness.SNAPSHOT.value}' in Phase L2")
        return v

    @field_validator("citation_required")
    @classmethod
    def _validate_citation_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("citation_required must be True in Phase L2")
        return v

    @field_validator("max_response_chars")
    @classmethod
    def _validate_max_response_chars(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_response_chars must be >= 1")
        return v

    @field_validator("timeout_ms")
    @classmethod
    def _validate_timeout_ms(cls, v: int) -> int:
        if v < 1:
            raise ValueError("timeout_ms must be >= 1")
        return v

    @field_validator("max_retries")
    @classmethod
    def _validate_max_retries(cls, v: int) -> int:
        if v != 0:
            raise ValueError("max_retries must be 0 in Phase L2")
        return v

    @field_validator("source_version")
    @classmethod
    def _validate_source_version(cls, v: str | None) -> str | None:
        if v is not None:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("source_version, when present, must be nonblank after trimming")
            return v.strip()
        return None


class SourcePolicy(BaseModel):
    """Caller constraints for source selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_source_ids: tuple[str, ...] = ()

    @field_validator("allowed_source_ids", mode="before")
    @classmethod
    def _coerce_tuple(cls, v: Any) -> Any:
        if isinstance(v, list):
            return tuple(v)
        return v

    @model_validator(mode="after")
    def _validate_policy(self) -> SourcePolicy:
        if len(self.allowed_source_ids) > 1:
            count = len(self.allowed_source_ids)
            raise LiteBridgeValidationError(
                f"At most one source ID may be specified in Phase L2, got {count}"
            )
        for s_id in self.allowed_source_ids:
            if not isinstance(s_id, str) or not SLUG_REGEX.match(s_id):
                raise ValueError(f"Invalid source_id slug in allowed_source_ids: '{s_id}'")
        return self


class EvidenceRecord(BaseModel):
    """Immutable, citation-safe record of a single piece of retrieved evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    citation_id: str = Field(min_length=1)
    source_kind: SourceKind = SourceKind.LOCAL_DOCUMENT
    source_id: str = Field(min_length=1)
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

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
    """Supported evidence source categories in LiteBridge."""

    LOCAL_DOCUMENT = "local_document"
    WEB_SEARCH_SNIPPET = "web_search_snippet"
    WEB_PAGE_EXCERPT = "web_page_excerpt"


class PrivacyClassification(StrEnum):
    """Supported privacy classification levels in LiteBridge."""

    PRIVATE = "private"
    PUBLIC_WEB = "public_web"


class SourceFreshness(StrEnum):
    """Supported data freshness classifications in LiteBridge."""

    SNAPSHOT = "snapshot"
    LIVE = "live"


class StopReason(StrEnum):
    """Explicit, typed reasons for concluding context preparation."""

    SUCCESS = "success"
    NO_EVIDENCE = "no_evidence"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    INVALID_QUERY = "invalid_query"
    RETRIEVAL_FAILED = "retrieval_failed"


class WebRetrievalPolicy(BaseModel):
    """Caller constraints for bounded web retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_external_query: bool = False
    max_search_results: int = Field(default=5, ge=1, le=5)
    fetch_pages: bool = False
    max_page_fetches: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def _validate_page_fetches(self) -> WebRetrievalPolicy:
        if not self.fetch_pages and self.max_page_fetches != 0:
            raise LiteBridgeValidationError("max_page_fetches must be 0 when fetch_pages is False")
        if self.fetch_pages and self.max_page_fetches < 1:
            raise LiteBridgeValidationError(
                "max_page_fetches must be at least 1 when fetch_pages is True"
            )
        return self


class RetrievalPolicy(BaseModel):
    """Caller constraints for bounded retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_ONLY
    mode: Literal["sparse", "dense", "hybrid"] = "hybrid"
    max_evidence_items: int = Field(default=6, ge=1, le=6)
    max_context_chars: int = Field(default=24000, ge=100, le=24000)
    max_estimated_tokens: int = Field(default=6000, ge=25, le=6000)
    web: WebRetrievalPolicy | None = None


SLUG_REGEX = re.compile(r"^[a-z0-9_-]+$")
HASH_HEX_REGEX = re.compile(r"^[0-9a-f]{64}$")
UTC_TIMESTAMP_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")


def validate_canonical_https_url(url: str) -> None:
    """Validate canonical HTTPS URL without credentials, fragments, or custom ports."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("canonical_url must be a nonblank string")
    if not url.startswith("https://"):
        raise ValueError("canonical_url must use the https scheme")
    if "@" in url:
        raise ValueError("canonical_url must not contain user credentials")
    if "#" in url:
        raise ValueError("canonical_url must not contain a URL fragment")
    rest = url[len("https://") :]
    slash_idx = rest.find("/")
    q_idx = rest.find("?")
    candidates = [i for i in [slash_idx, q_idx, len(rest)] if i >= 0]
    end_idx = min(candidates)
    host_port = rest[:end_idx]
    if not host_port:
        raise ValueError("canonical_url must contain a hostname")
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        if port != "443":
            raise ValueError("canonical_url must not specify a non-default port")
    else:
        host = host_port
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        raise ValueError("canonical_url must not be an IP-literal host")
    if host.startswith("[") or host.endswith("]"):
        raise ValueError("canonical_url must not be an IPv6 literal")


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
    supported_execution_profiles: tuple[ExecutionProfile, ...] = (ExecutionProfile.LOCAL_ONLY,)

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

    @field_validator("citation_required")
    @classmethod
    def _validate_citation_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("citation_required must be True in Phase L3")
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
            raise ValueError("max_retries must be 0 in Phase L3")
        return v

    @field_validator("source_version")
    @classmethod
    def _validate_source_version(cls, v: str | None) -> str | None:
        if v is not None:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("source_version, when present, must be nonblank after trimming")
            return v.strip()
        return None

    @model_validator(mode="after")
    def _validate_descriptor_constraints(self) -> SourceDescriptor:
        if self.source_kind == SourceKind.LOCAL_DOCUMENT:
            if self.privacy_classification != PrivacyClassification.PRIVATE:
                val = PrivacyClassification.PRIVATE.value
                raise ValueError(f"Local document source must have privacy '{val}'")
            if self.freshness != SourceFreshness.SNAPSHOT:
                val = SourceFreshness.SNAPSHOT.value
                raise ValueError(f"Local document source must have freshness '{val}'")
            if ExecutionProfile.LOCAL_ONLY not in self.supported_execution_profiles:
                raise ValueError("Local document source must support LOCAL_ONLY profile")
        elif self.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
            if self.privacy_classification != PrivacyClassification.PUBLIC_WEB:
                val = PrivacyClassification.PUBLIC_WEB.value
                raise ValueError(f"Web search source must have privacy '{val}'")
            if self.freshness != SourceFreshness.LIVE:
                val = SourceFreshness.LIVE.value
                raise ValueError(f"Web search source must have freshness '{val}'")
            if self.supported_execution_profiles != (ExecutionProfile.HYBRID,):
                raise ValueError("Web search source supports only HYBRID profile")
        else:
            raise ValueError(f"Unsupported registered source_kind: '{self.source_kind}'")
        return self


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
                f"At most one source ID may be specified in Phase L3, got {count}"
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
    canonical_url: str | None = None
    content_hash: str | None = None
    fetched_at_utc: str | None = None
    metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_provenance(self) -> EvidenceRecord:
        if self.source_kind == SourceKind.LOCAL_DOCUMENT:
            if (
                self.canonical_url is not None
                or self.content_hash is not None
                or self.fetched_at_utc is not None
            ):
                raise ValueError(
                    "Local document records must not specify canonical_url, content_hash, "
                    "or fetched_at_utc"
                )
        elif self.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
            if self.canonical_url is None:
                raise ValueError("Web search snippet records require canonical_url")
            validate_canonical_https_url(self.canonical_url)
            if self.fetched_at_utc is not None:
                raise ValueError("Web search snippet records must not specify fetched_at_utc")
        elif self.source_kind == SourceKind.WEB_PAGE_EXCERPT:
            if self.canonical_url is None:
                raise ValueError("Web page excerpt records require canonical_url")
            validate_canonical_https_url(self.canonical_url)
            if self.content_hash is None or not HASH_HEX_REGEX.match(self.content_hash):
                raise ValueError("Web page excerpt records require a 64-char SHA-256 content_hash")
            if self.fetched_at_utc is None or not UTC_TIMESTAMP_REGEX.match(self.fetched_at_utc):
                raise ValueError("Web page excerpt records require a valid UTC timestamp")
        return self


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
    web_calls: int = Field(default=0, ge=0)
    retrieval_route: str = Field(min_length=1)
    timings_ms: tuple[tuple[str, float], ...] = Field(default_factory=tuple)
    stop_reason: StopReason
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    reproducibility: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

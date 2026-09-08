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


class BudgetPolicy(BaseModel):
    """Caller limits for execution calls, timing, and estimated external costs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_retrieval_calls: int = Field(default=1, ge=0, le=1)
    max_web_calls: int = Field(default=0, ge=0, le=1)
    max_wall_clock_ms: int = Field(default=10000, ge=100, le=60000)
    max_estimated_external_cost_microusd: int = Field(
        default=0,
        ge=0,
        le=1_000_000,
    )


class PlannerRoute(StrEnum):
    """Routing decisions emitted by the deterministic planner."""

    LOCAL = "local"
    WEB = "web"
    BLOCKED = "blocked"


class PlannerReason(StrEnum):
    """Explainable reason codes for planner and budget decisions."""

    CALLER_SELECTED_SOURCE = "caller_selected_source"
    DEFAULT_LOCAL = "default_local"
    FRESHNESS_CUE = "freshness_cue"
    EXTERNAL_QUERY_NOT_ALLOWED = "external_query_not_allowed"
    WEB_SOURCE_UNAVAILABLE = "web_source_unavailable"
    WEB_CALL_BUDGET_EXHAUSTED = "web_call_budget_exhausted"
    EXTERNAL_COST_BUDGET_EXHAUSTED = "external_cost_budget_exhausted"
    RETRIEVAL_BUDGET_EXHAUSTED = "retrieval_budget_exhausted"
    INVALID_PROFILE = "invalid_profile"


class QueryFeatures(BaseModel):
    """Deterministic, planner-safe features extracted from the query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_length: int = Field(ge=0)
    token_like_count: int = Field(ge=0)
    has_freshness_cue: bool
    has_local_reference_cue: bool
    has_explicit_time_reference: bool


class PlannerDecision(BaseModel):
    """Immutable, explainable decision produced by the deterministic planner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planner_id: str = "deterministic_heuristic"
    planner_version: str = "l4_v1"
    route: PlannerRoute
    selected_source_id: str | None = None
    reason_codes: tuple[PlannerReason, ...] = ()
    features: QueryFeatures
    effective_budget: BudgetPolicy

    @field_validator("reason_codes", mode="before")
    @classmethod
    def _coerce_tuple(cls, v: Any) -> Any:
        if isinstance(v, list):
            return tuple(v)
        return v

    @model_validator(mode="after")
    def _validate_decision(self) -> PlannerDecision:
        if self.planner_id != "deterministic_heuristic":
            raise ValueError("planner_id must be 'deterministic_heuristic'")
        if self.planner_version != "l4_v1":
            raise ValueError("planner_version must be 'l4_v1'")
        if self.route == PlannerRoute.BLOCKED:
            if self.selected_source_id is not None:
                raise ValueError("selected_source_id must be None when route is BLOCKED")
        elif self.route in (PlannerRoute.LOCAL, PlannerRoute.WEB):
            if not self.selected_source_id or not isinstance(self.selected_source_id, str):
                raise ValueError(
                    f"selected_source_id must be a nonblank string when route is {self.route.value}"
                )
        return self


class WebRetrievalPolicy(BaseModel):
    """Caller constraints for bounded web retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_external_query: bool = False
    max_search_results: int = Field(default=5, ge=1, le=5)


class RetrievalPolicy(BaseModel):
    """Caller constraints for bounded retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_ONLY
    mode: Literal["sparse", "dense", "hybrid"] = "hybrid"
    max_evidence_items: int = Field(default=6, ge=1, le=6)
    max_context_chars: int = Field(default=24000, ge=100, le=24000)
    max_estimated_tokens: int = Field(default=6000, ge=25, le=6000)
    web: WebRetrievalPolicy | None = None
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)

    @model_validator(mode="before")
    @classmethod
    def _default_budget(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "budget" not in data or data["budget"] is None:
                web_data = data.get("web")
                allow_web = False
                if isinstance(web_data, dict):
                    allow_web = bool(web_data.get("allow_external_query", False))
                elif isinstance(web_data, WebRetrievalPolicy):
                    allow_web = web_data.allow_external_query
                if allow_web and data.get("execution_profile") == ExecutionProfile.HYBRID:
                    data["budget"] = BudgetPolicy(
                        max_retrieval_calls=1,
                        max_web_calls=1,
                        max_estimated_external_cost_microusd=1_000_000,
                    )
                else:
                    data["budget"] = BudgetPolicy()
        return data


SLUG_REGEX = re.compile(r"^[a-z0-9_-]+$")


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
    estimated_external_cost_microusd: int = Field(default=0, ge=0)

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
    metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_provenance(self) -> EvidenceRecord:
        if self.source_kind == SourceKind.LOCAL_DOCUMENT:
            if self.canonical_url is not None:
                raise ValueError("Local document records must not specify canonical_url")
        elif self.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
            if self.canonical_url is None:
                raise ValueError("Web search snippet records require canonical_url")
            validate_canonical_https_url(self.canonical_url)
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
    planner_decision: PlannerDecision
    budget_used: tuple[tuple[str, int], ...] = Field(default_factory=tuple)

    @field_validator("budget_used", mode="before")
    @classmethod
    def _coerce_budget_used(cls, v: Any) -> Any:
        if isinstance(v, list):
            return tuple(tuple(item) if isinstance(item, list) else item for item in v)
        return v

    @model_validator(mode="after")
    def _validate_budget_used(self) -> ContextPackage:
        expected_keys = (
            "estimated_external_cost_microusd",
            "retrieval_calls",
            "wall_clock_ms",
            "web_calls",
        )
        if self.budget_used:
            actual_keys = tuple(k for k, _ in self.budget_used)
            if actual_keys != expected_keys:
                raise ValueError(
                    f"budget_used keys must match {expected_keys} in order, got {actual_keys}"
                )
            for k, v in self.budget_used:
                if not isinstance(v, int) or v < 0:
                    raise ValueError(
                        f"budget_used value for '{k}' must be a non-negative int, got {v}"
                    )
        return self


class ProviderLocation(StrEnum):
    """Execution location of a generation provider."""

    LOCAL = "local"
    HOSTED = "hosted"


class GenerationStatus(StrEnum):
    """Explicit status outcomes of answer generation."""

    SUCCESS = "success"
    ABSTAINED = "abstained"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_CITATIONS = "invalid_citations"
    POLICY_BLOCKED = "policy_blocked"
    GENERATION_FAILED = "generation_failed"


class GenerationAbstentionReason(StrEnum):
    """Typed reasons for abstaining from answer generation."""

    NO_EVIDENCE = "no_evidence"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    EXTERNAL_GENERATION_NOT_ALLOWED = "external_generation_not_allowed"
    PRIVATE_EVIDENCE_EXPORT_NOT_ALLOWED = "private_evidence_export_not_allowed"
    INVALID_CITATIONS = "invalid_citations"
    PROVIDER_FAILURE = "provider_failure"


class GenerationPolicy(BaseModel):
    """Immutable policy governing answer generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(
        default="local_ollama",
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9_]+$",
    )
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=512, ge=1, le=2048)
    timeout_ms: int = Field(default=30000, ge=1000, le=60000)
    allow_external_generation: bool = False
    allow_private_evidence_export: bool = False


class ProviderCapability(BaseModel):
    """Immutable capability descriptor for a registered generation provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    location: ProviderLocation
    model_id: str = Field(min_length=1)
    supports_citations: bool
    max_output_tokens: int = Field(ge=1)
    enabled: bool


class GenerationUsage(BaseModel):
    """Normalized token usage reported directly by a generation provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class GroundedAnswer(BaseModel):
    """Immutable, citation-gated answer produced by LiteBridge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_id: str = Field(min_length=1)
    context_package_id: str = Field(min_length=1)
    provider_id: str | None = None
    model_id: str | None = None
    status: GenerationStatus
    text: str
    cited_evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    citation_valid: bool
    abstention_reason: GenerationAbstentionReason | None = None
    usage: GenerationUsage = Field(default_factory=GenerationUsage)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    timings_ms: tuple[tuple[str, float], ...] = Field(default_factory=tuple)

    @field_validator("cited_evidence_ids", "warnings", mode="before")
    @classmethod
    def _coerce_tuples(cls, v: Any) -> Any:
        if isinstance(v, list):
            return tuple(v)
        return v

    @field_validator("timings_ms", mode="before")
    @classmethod
    def _coerce_timings(cls, v: Any) -> Any:
        if isinstance(v, list):
            return tuple(tuple(item) if isinstance(item, list) else item for item in v)
        return v

    @model_validator(mode="after")
    def _validate_status_citation_invariants(self) -> GroundedAnswer:
        if self.status != GenerationStatus.SUCCESS and self.citation_valid:
            raise ValueError("citation_valid must be False when generation status is not SUCCESS")
        return self


def derive_answer_id(
    *,
    context_package_id: str,
    provider_id: str | None,
    model_id: str | None,
    policy: GenerationPolicy,
    text: str,
    status: GenerationStatus,
    cited_evidence_ids: tuple[str, ...],
    abstention_reason: GenerationAbstentionReason | None = None,
) -> str:
    """Derive a deterministic answer ID strictly from stable execution inputs."""
    import hashlib

    hasher = hashlib.sha256()
    hasher.update(context_package_id.encode())
    hasher.update((provider_id or "").encode())
    hasher.update((model_id or "").encode())
    hasher.update(policy.provider_id.encode())
    hasher.update(f"{policy.temperature:.4f}".encode())
    hasher.update(str(policy.max_output_tokens).encode())
    hasher.update(str(policy.allow_external_generation).encode())
    hasher.update(str(policy.allow_private_evidence_export).encode())
    hasher.update(hashlib.sha256(text.encode()).digest())
    hasher.update(status.value.encode())
    hasher.update((abstention_reason.value if abstention_reason else "").encode())
    for cid in sorted(cited_evidence_ids):
        hasher.update(cid.encode())
    return f"ans_{hasher.hexdigest()[:24]}"

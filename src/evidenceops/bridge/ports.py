"""Provider-neutral port protocols and candidate types for LiteBridge."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidenceops.bridge.contracts import (
    GenerationPolicy,
    ProviderCapability,
    RetrievalPolicy,
    SourceKind,
    validate_canonical_https_url,
)


class RawEvidenceCandidate(BaseModel):
    """LiteBridge-neutral raw candidate returned by an EvidenceRetriever port implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    source_kind: SourceKind = SourceKind.LOCAL_DOCUMENT
    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_id: str | None = None
    title: str = ""
    section: str = ""
    source_label: str = ""
    text: str = Field(min_length=1)
    retrieval_route: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = 0.0
    source_version: str | None = None
    canonical_url: str | None = None
    metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_provenance(self) -> RawEvidenceCandidate:
        if self.source_kind == SourceKind.LOCAL_DOCUMENT:
            if self.canonical_url is not None:
                raise ValueError("Local document candidates must not specify canonical_url")
        elif self.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
            if self.canonical_url is None:
                raise ValueError("Web search snippet candidates require canonical_url")
            validate_canonical_https_url(self.canonical_url)
        return self


class WebSearchHit(BaseModel):
    """Normalized search result hit from a WebSearchProvider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    url: str
    snippet: str
    rank: int = Field(ge=1)


class RetrievalBatch(BaseModel):
    """Normalized batch of candidates returned by a single retrieval call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[RawEvidenceCandidate, ...] = Field(default_factory=tuple)
    retrieval_calls: int = Field(default=1, ge=1)
    web_calls: int = Field(default=0, ge=0)
    retrieval_route: str = "hybrid"
    timings_ms: tuple[tuple[str, float], ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    reproducibility: tuple[tuple[str, str], ...] = Field(default_factory=tuple)


@runtime_checkable
class EvidenceRetriever(Protocol):
    """Provider-neutral port for retrieving evidence candidates."""

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        """Execute a single bounded retrieval operation."""
        ...


@runtime_checkable
class WebSearchProvider(Protocol):
    """Provider-neutral port for web search operations."""

    def search(
        self,
        query: str,
        *,
        max_results: int,
        timeout_ms: int,
    ) -> tuple[WebSearchHit, ...]:
        """Execute web search query returning normalized hits."""
        ...


class GenerationRequest(BaseModel):
    """LiteBridge-neutral request passed to a GenerationProvider port."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_package_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    system_instruction: str = Field(min_length=1)
    context_text: str
    max_output_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0.0, le=1.0)


class GenerationResponse(BaseModel):
    """LiteBridge-neutral response returned by a GenerationProvider port."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    model_id: str = Field(min_length=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


@runtime_checkable
class GenerationProvider(Protocol):
    """Provider-neutral port for answer generation."""

    @property
    def capability(self) -> ProviderCapability:
        """Return the capability descriptor for this provider."""
        ...

    def generate(
        self,
        request: GenerationRequest,
        policy: GenerationPolicy,
    ) -> GenerationResponse:
        """Execute a single bounded generation call."""
        ...

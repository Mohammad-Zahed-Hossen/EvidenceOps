"""Provider-neutral port protocols and candidate types for LiteBridge."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidenceops.bridge.contracts import (
    HASH_HEX_REGEX,
    UTC_TIMESTAMP_REGEX,
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
    content_hash: str | None = None
    fetched_at_utc: str | None = None
    metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_provenance(self) -> RawEvidenceCandidate:
        if self.source_kind == SourceKind.LOCAL_DOCUMENT:
            if (
                self.canonical_url is not None
                or self.content_hash is not None
                or self.fetched_at_utc is not None
            ):
                raise ValueError(
                    "Local document candidates must not specify canonical_url, content_hash, "
                    "or fetched_at_utc"
                )
        elif self.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
            if self.canonical_url is None:
                raise ValueError("Web search snippet candidates require canonical_url")
            validate_canonical_https_url(self.canonical_url)
            if self.fetched_at_utc is not None:
                raise ValueError("Web search snippet candidates must not specify fetched_at_utc")
        elif self.source_kind == SourceKind.WEB_PAGE_EXCERPT:
            if self.canonical_url is None:
                raise ValueError("Web page excerpt candidates require canonical_url")
            validate_canonical_https_url(self.canonical_url)
            if self.content_hash is None or not HASH_HEX_REGEX.match(self.content_hash):
                raise ValueError(
                    "Web page excerpt candidates require a 64-char SHA-256 content_hash"
                )
            if self.fetched_at_utc is None or not UTC_TIMESTAMP_REGEX.match(self.fetched_at_utc):
                raise ValueError("Web page excerpt candidates require a valid UTC timestamp")
        return self


class WebSearchHit(BaseModel):
    """Normalized search result hit from a WebSearchProvider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    url: str
    snippet: str
    rank: int = Field(ge=1)


class FetchedWebPage(BaseModel):
    """Normalized fetched page result from a WebPageFetcher."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_url: str
    title: str
    text: str
    content_hash: str
    fetched_at_utc: str


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


@runtime_checkable
class WebPageFetcher(Protocol):
    """Provider-neutral port for safe web page fetching."""

    def fetch(
        self,
        url: str,
        *,
        timeout_ms: int,
        max_response_bytes: int,
        allowed_domains: tuple[str, ...],
        max_redirects: int,
    ) -> FetchedWebPage:
        """Fetch and extract untrusted text from a URL matching the domain allowlist."""
        ...

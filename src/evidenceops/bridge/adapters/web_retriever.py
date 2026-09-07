"""Combined EvidenceRetriever adapter for Tavily search and safe page fetching."""

from __future__ import annotations

import hashlib
import time
from urllib.parse import urlparse

from evidenceops.bridge.adapters.web_cache import WebRetrievalCache
from evidenceops.bridge.contracts import (
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
)
from evidenceops.bridge.errors import (
    LiteBridgeProfileError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import (
    EvidenceRetriever,
    RawEvidenceCandidate,
    RetrievalBatch,
    WebPageFetcher,
    WebSearchProvider,
)


class WebRetrieverAdapter(EvidenceRetriever):
    """Retrieves web evidence using a search provider and optional safe page fetcher."""

    def __init__(
        self,
        search_provider: WebSearchProvider,
        page_fetcher: WebPageFetcher,
        cache: WebRetrievalCache | None = None,
        source_id: str = "tavily_web_search",
        adapter_id: str = "tavily_web",
        allowed_domains: tuple[str, ...] = (),
        max_configured_results: int = 5,
        max_configured_page_fetches: int = 2,
        timeout_ms: int = 5000,
        max_response_bytes: int = 200_000,
        max_redirects: int = 3,
        reproducibility: tuple[tuple[str, str], ...] = (
            ("provider", "tavily"),
            ("search_depth", "basic"),
        ),
    ) -> None:
        self._search_provider = search_provider
        self._page_fetcher = page_fetcher
        self._cache = cache
        self._source_id = source_id
        self._adapter_id = adapter_id
        self._allowed_domains = allowed_domains
        self._max_configured_results = max_configured_results
        self._max_configured_page_fetches = max_configured_page_fetches
        self._timeout_ms = timeout_ms
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._reproducibility = reproducibility

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        """Retrieve web evidence according to the provided policy and limits."""
        if policy.execution_profile != ExecutionProfile.HYBRID:
            raise LiteBridgeProfileError(
                f"WebRetrieverAdapter requires 'hybrid' execution profile, "
                f"got '{policy.execution_profile.value}'"
            )

        if policy.web is None or not policy.web.allow_external_query:
            raise LiteBridgeValidationError(
                "WebRetrieverAdapter requires WebRetrievalPolicy with allow_external_query=True"
            )

        # Enforce policy-to-settings caps
        effective_results = min(
            policy.web.max_search_results,
            self._max_configured_results,
        )
        effective_page_fetches = min(
            policy.web.max_page_fetches,
            self._max_configured_page_fetches,
        )

        # Check cache
        if self._cache is not None:
            cached_candidates = self._cache.get(self._source_id, query, policy.web)
            if cached_candidates is not None:
                return RetrievalBatch(
                    candidates=cached_candidates,
                    retrieval_calls=1,
                    web_calls=0,
                    retrieval_route="web_cached",
                    timings_ms=(("web_retrieval", 0.0),),
                    warnings=(),
                    reproducibility=self._reproducibility,
                )

        t0 = time.perf_counter()
        warnings: list[str] = []
        web_calls = 0

        # Execute search
        hits = self._search_provider.search(
            query,
            max_results=effective_results,
            timeout_ms=self._timeout_ms,
        )
        web_calls += 1

        if not hits:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return RetrievalBatch(
                candidates=(),
                retrieval_calls=1,
                web_calls=web_calls,
                retrieval_route="web_search",
                timings_ms=(("web_retrieval", elapsed_ms),),
                warnings=tuple(warnings),
                reproducibility=self._reproducibility,
            )

        candidates: list[RawEvidenceCandidate] = []
        page_fetches_done = 0

        for rank, hit in enumerate(hits, start=1):
            use_fetched_page = False
            fetched = None

            if (
                policy.web.fetch_pages
                and effective_page_fetches > 0
                and page_fetches_done < effective_page_fetches
            ):
                if not self._allowed_domains:
                    if "Page fetching disabled: allowed_fetch_domains is empty" not in warnings:
                        warnings.append("Page fetching disabled: allowed_fetch_domains is empty")
                else:
                    parsed_host = (urlparse(hit.url).hostname or "").lower()
                    if parsed_host in self._allowed_domains:
                        try:
                            fetched = self._page_fetcher.fetch(
                                hit.url,
                                timeout_ms=self._timeout_ms,
                                max_response_bytes=self._max_response_bytes,
                                allowed_domains=self._allowed_domains,
                                max_redirects=self._max_redirects,
                            )
                            web_calls += 1
                            if fetched is not None:
                                use_fetched_page = True
                                page_fetches_done += 1
                            else:
                                warnings.append(
                                    f"Failed to fetch page for '{hit.url}'; falling back to snippet"
                                )
                        except Exception as exc:
                            web_calls += 1
                            warnings.append(
                                f"Error fetching page for '{hit.url}': {exc}; "
                                "falling back to snippet"
                            )

            if use_fetched_page and fetched is not None:
                source_kind = SourceKind.WEB_PAGE_EXCERPT
                text = fetched.text
                canonical_url = fetched.canonical_url
                content_hash = fetched.content_hash
                fetched_at_utc = fetched.fetched_at_utc
                section = "page_content"
            else:
                source_kind = SourceKind.WEB_SEARCH_SNIPPET
                text = hit.snippet
                canonical_url = hit.url
                content_hash = hashlib.sha256(hit.snippet.encode("utf-8")).hexdigest()
                fetched_at_utc = None
                section = "search_snippet"

            candidate_id = f"cand_web_{rank}_{content_hash[:8]}"
            candidate = RawEvidenceCandidate(
                candidate_id=candidate_id,
                source_kind=source_kind,
                source_id=self._source_id,
                document_id=canonical_url,
                chunk_id=f"hit_{rank}",
                title=hit.title,
                section=section,
                source_label=f"Web: {hit.title}",
                text=text,
                retrieval_route="web_search",
                rank=rank,
                score=1.0 / rank,
                source_version=None,
                canonical_url=canonical_url,
                content_hash=content_hash,
                fetched_at_utc=fetched_at_utc,
                metadata=(
                    ("url", hit.url),
                    ("rank", str(hit.rank)),
                ),
            )
            candidates.append(candidate)

        candidates_tuple = tuple(candidates)

        if self._cache is not None:
            self._cache.put(self._source_id, query, policy.web, candidates_tuple)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return RetrievalBatch(
            candidates=candidates_tuple,
            retrieval_calls=1,
            web_calls=web_calls,
            retrieval_route="web_search",
            timings_ms=(("web_retrieval", elapsed_ms),),
            warnings=tuple(warnings),
            reproducibility=self._reproducibility,
        )

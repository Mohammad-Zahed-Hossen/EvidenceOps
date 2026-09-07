"""EvidenceRetriever adapter for Tavily search snippet retrieval."""

from __future__ import annotations

import hashlib
import time

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
    WebSearchProvider,
)


class WebRetrieverAdapter(EvidenceRetriever):
    """Retrieves web evidence using a search provider in snippet-only mode."""

    def __init__(
        self,
        search_provider: WebSearchProvider,
        cache: WebRetrievalCache | None = None,
        source_id: str = "tavily_web_search",
        adapter_id: str = "tavily_web",
        max_configured_results: int = 5,
        timeout_ms: int = 5000,
        reproducibility: tuple[tuple[str, str], ...] = (
            ("provider", "tavily"),
            ("search_depth", "basic"),
        ),
    ) -> None:
        self._search_provider = search_provider
        self._cache = cache
        self._source_id = source_id
        self._adapter_id = adapter_id
        self._max_configured_results = max_configured_results
        self._timeout_ms = timeout_ms
        self._reproducibility = reproducibility

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        """Retrieve web evidence snippets according to the provided policy and limits."""
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
        for rank, hit in enumerate(hits, start=1):
            text = hit.snippet
            canonical_url = hit.url
            content_hash = hashlib.sha256(hit.snippet.encode("utf-8")).hexdigest()
            candidate_id = f"cand_web_{rank}_{content_hash[:8]}"

            candidate = RawEvidenceCandidate(
                candidate_id=candidate_id,
                source_kind=SourceKind.WEB_SEARCH_SNIPPET,
                source_id=self._source_id,
                document_id=canonical_url,
                chunk_id=f"hit_{rank}",
                title=hit.title,
                section="search_snippet",
                source_label=f"Web: {hit.title}",
                text=text,
                retrieval_route="web_search",
                rank=rank,
                score=1.0 / rank,
                source_version=None,
                canonical_url=canonical_url,
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

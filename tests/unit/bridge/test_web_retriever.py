"""Unit tests for WebRetrieverAdapter coordinating search, safe fetch, and caching."""

from __future__ import annotations

import pytest

from evidenceops.bridge.adapters.web_cache import WebRetrievalCache
from evidenceops.bridge.adapters.web_retriever import WebRetrieverAdapter
from evidenceops.bridge.contracts import (
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
    WebRetrievalPolicy,
)
from evidenceops.bridge.errors import (
    LiteBridgeProfileError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import FetchedWebPage, WebSearchHit


class FakeSearchProvider:
    def __init__(self, hits: list[WebSearchHit]) -> None:
        self.hits = hits
        self.last_query: str | None = None
        self.last_max_results: int | None = None
        self.call_count = 0

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        timeout_ms: int = 5000,
    ) -> tuple[WebSearchHit, ...]:
        self.call_count += 1
        self.last_query = query
        self.last_max_results = max_results
        return tuple(self.hits[:max_results])


class FakePageFetcher:
    def __init__(self, pages_by_url: dict[str, FetchedWebPage | None]) -> None:
        self.pages_by_url = pages_by_url
        self.fetches: list[str] = []

    def fetch(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        max_response_bytes: int | None = None,
        allowed_domains: tuple[str, ...] | None = None,
        max_redirects: int | None = None,
    ) -> FetchedWebPage | None:
        self.fetches.append(url)
        if url in self.pages_by_url:
            val = self.pages_by_url[url]
            if isinstance(val, Exception):
                raise val
            return val
        return None

    def fetch_page(self, url: str) -> FetchedWebPage | None:
        return self.fetch(url)


def test_web_retriever_requires_hybrid_and_consent() -> None:
    search_provider = FakeSearchProvider([])
    fetcher = FakePageFetcher({})
    adapter = WebRetrieverAdapter(search_provider, fetcher)

    local_policy = RetrievalPolicy(execution_profile=ExecutionProfile.LOCAL_ONLY)
    with pytest.raises(LiteBridgeProfileError):
        adapter.retrieve("test", local_policy)

    hybrid_no_web = RetrievalPolicy(execution_profile=ExecutionProfile.HYBRID, web=None)
    with pytest.raises(LiteBridgeValidationError):
        adapter.retrieve("test", hybrid_no_web)

    hybrid_no_consent = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=False),
    )
    with pytest.raises(LiteBridgeValidationError):
        adapter.retrieve("test", hybrid_no_consent)


def test_web_retriever_coordination_and_page_fetch() -> None:
    hits = [
        WebSearchHit(
            title="FastAPI Home",
            url="https://fastapi.tiangolo.com/",
            snippet="FastAPI framework snippet",
            rank=1,
        ),
        WebSearchHit(
            title="Other Docs",
            url="https://other.org/guide",
            snippet="Other guide snippet",
            rank=2,
        ),
    ]
    pages = {
        "https://fastapi.tiangolo.com/": FetchedWebPage(
            canonical_url="https://fastapi.tiangolo.com/",
            title="FastAPI Full Title",
            text="FastAPI extracted full text from web page",
            content_hash="a" * 64,
            fetched_at_utc="2026-09-07T12:00:00Z",
        )
    }

    search_provider = FakeSearchProvider(hits)
    fetcher = FakePageFetcher(pages)
    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        page_fetcher=fetcher,
        allowed_domains=("fastapi.tiangolo.com",),
        max_configured_results=5,
        max_configured_page_fetches=2,
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(
            allow_external_query=True,
            fetch_pages=True,
            max_page_fetches=2,
        ),
    )

    batch = adapter.retrieve("fastapi tutorial", policy)

    assert len(batch.candidates) == 2
    assert batch.web_calls == 2  # 1 search + 1 fetch
    # First candidate is fetched page
    assert batch.candidates[0].source_kind == SourceKind.WEB_PAGE_EXCERPT
    assert batch.candidates[0].text == "FastAPI extracted full text from web page"
    assert batch.candidates[0].canonical_url == "https://fastapi.tiangolo.com/"
    # Second candidate is search snippet because domain is not allowed
    assert batch.candidates[1].source_kind == SourceKind.WEB_SEARCH_SNIPPET
    assert batch.candidates[1].text == "Other guide snippet"


def test_web_retriever_enforces_policy_to_settings_caps() -> None:
    hits = [
        WebSearchHit(title=f"Hit {i}", url=f"https://doc.org/{i}", snippet=f"s{i}", rank=i + 1)
        for i in range(10)
    ]
    search_provider = FakeSearchProvider(hits)
    fetcher = FakePageFetcher({})

    # Configured caps: max 2 search results, max 1 page fetch
    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        page_fetcher=fetcher,
        allowed_domains=("doc.org",),
        max_configured_results=2,
        max_configured_page_fetches=1,
    )

    # Caller requests 5 search results and 3 page fetches
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(
            allow_external_query=True,
            max_search_results=5,
            fetch_pages=True,
            max_page_fetches=3,
        ),
    )

    batch = adapter.retrieve("query", policy)

    # Search provider should have received clamped max_results=2
    assert search_provider.last_max_results == 2
    assert len(batch.candidates) == 2


def test_web_retriever_caching() -> None:
    hits = [
        WebSearchHit(
            title="FastAPI",
            url="https://fastapi.tiangolo.com/",
            snippet="FastAPI snippet",
            rank=1,
        )
    ]
    search_provider = FakeSearchProvider(hits)
    fetcher = FakePageFetcher({})
    cache = WebRetrievalCache(max_entries=10, ttl_seconds=60)

    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        page_fetcher=fetcher,
        cache=cache,
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True, fetch_pages=False),
    )

    # First call: miss
    batch1 = adapter.retrieve("query", policy)
    assert search_provider.call_count == 1
    assert batch1.web_calls == 1
    assert batch1.retrieval_route == "web_search"

    # Second call: hit
    batch2 = adapter.retrieve("query", policy)
    assert search_provider.call_count == 1  # Not incremented
    assert batch2.web_calls == 0  # 0 live web calls
    assert batch2.retrieval_route == "web_cached"
    assert len(batch2.candidates) == len(batch1.candidates)


def test_web_retriever_fetch_failure_falls_back_to_snippet() -> None:
    hits = [
        WebSearchHit(
            title="FastAPI Home",
            url="https://fastapi.tiangolo.com/",
            snippet="Fallback snippet",
            rank=1,
        )
    ]
    search_provider = FakeSearchProvider(hits)
    # Page fetcher returns None (failure)
    fetcher = FakePageFetcher({"https://fastapi.tiangolo.com/": None})

    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        page_fetcher=fetcher,
        allowed_domains=("fastapi.tiangolo.com",),
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(
            allow_external_query=True,
            fetch_pages=True,
            max_page_fetches=1,
        ),
    )

    batch = adapter.retrieve("query", policy)

    assert len(batch.candidates) == 1
    assert batch.candidates[0].source_kind == SourceKind.WEB_SEARCH_SNIPPET
    assert batch.candidates[0].text == "Fallback snippet"
    assert any("falling back to snippet" in w for w in batch.warnings)

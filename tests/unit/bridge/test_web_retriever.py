"""Unit tests for WebRetrieverAdapter coordinating search snippets and caching."""

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
from evidenceops.bridge.ports import WebSearchHit


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


def test_web_retriever_requires_hybrid_and_consent() -> None:
    search_provider = FakeSearchProvider([])
    adapter = WebRetrieverAdapter(search_provider)

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


def test_web_retriever_rejects_page_fetcher_injection() -> None:
    search_provider = FakeSearchProvider([])
    with pytest.raises(TypeError):
        WebRetrieverAdapter(search_provider, page_fetcher="dummy")  # type: ignore[call-arg]


def test_web_retriever_produces_snippets_only() -> None:
    hits = [
        WebSearchHit(
            title="FastAPI Home",
            url="https://fastapi.tiangolo.com/",
            snippet="FastAPI framework snippet",
            rank=1,
        ),
        WebSearchHit(
            title="Other Docs",
            url="https://docs.python.org/3/",
            snippet="Python guide snippet",
            rank=2,
        ),
    ]

    search_provider = FakeSearchProvider(hits)
    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        max_configured_results=5,
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
    )

    batch = adapter.retrieve("fastapi tutorial", policy)

    assert len(batch.candidates) == 2
    assert batch.web_calls == 1
    assert batch.retrieval_calls == 1

    for c in batch.candidates:
        assert c.source_kind == SourceKind.WEB_SEARCH_SNIPPET
        assert c.canonical_url is not None
        assert not hasattr(c, "content_hash") or getattr(c, "content_hash", None) is None
        assert not hasattr(c, "fetched_at_utc") or getattr(c, "fetched_at_utc", None) is None

    assert batch.candidates[0].text == "FastAPI framework snippet"
    assert batch.candidates[0].canonical_url == "https://fastapi.tiangolo.com/"
    assert batch.candidates[1].text == "Python guide snippet"
    assert batch.candidates[1].canonical_url == "https://docs.python.org/3/"


def test_web_retriever_enforces_policy_to_settings_caps() -> None:
    hits = [
        WebSearchHit(title=f"Hit {i}", url=f"https://doc.org/{i}", snippet=f"s{i}", rank=i + 1)
        for i in range(10)
    ]
    search_provider = FakeSearchProvider(hits)

    # Configured cap: max 2 search results
    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        max_configured_results=2,
    )

    # Caller requests 5 search results
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(
            allow_external_query=True,
            max_search_results=5,
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
    cache = WebRetrievalCache(max_entries=10, ttl_seconds=60)

    adapter = WebRetrieverAdapter(
        search_provider=search_provider,
        cache=cache,
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
    )

    # First call: cache miss
    batch1 = adapter.retrieve("query", policy)
    assert search_provider.call_count == 1
    assert batch1.retrieval_calls == 1
    assert batch1.web_calls == 1
    assert batch1.retrieval_route == "web_search"

    # Second call: cache hit
    batch2 = adapter.retrieve("query", policy)
    assert search_provider.call_count == 1  # Not incremented
    assert batch2.retrieval_calls == 1
    assert batch2.web_calls == 0  # 0 live web calls
    assert batch2.retrieval_route == "web_cached"
    assert len(batch2.candidates) == len(batch1.candidates)


def test_web_retriever_empty_hits() -> None:
    search_provider = FakeSearchProvider([])
    adapter = WebRetrieverAdapter(search_provider)

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
    )

    batch = adapter.retrieve("query", policy)
    assert batch.candidates == ()
    assert batch.retrieval_calls == 1
    assert batch.web_calls == 1
    assert batch.retrieval_route == "web_search"

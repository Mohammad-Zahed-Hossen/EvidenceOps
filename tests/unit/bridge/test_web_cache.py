"""Unit tests for WebRetrievalCache including TTL, LRU eviction, and thread safety."""

from __future__ import annotations

import concurrent.futures

from evidenceops.bridge.adapters.web_cache import WebRetrievalCache
from evidenceops.bridge.contracts import SourceKind, WebRetrievalPolicy
from evidenceops.bridge.ports import RawEvidenceCandidate


def _make_candidate(cand_id: str) -> RawEvidenceCandidate:
    return RawEvidenceCandidate(
        candidate_id=cand_id,
        source_id="web_source",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        document_id=cand_id,
        chunk_id=cand_id,
        title="Title",
        section="snippet",
        source_label="https://example.com",
        canonical_url="https://example.com",
        text="text",
        retrieval_route="web_search",
        rank=1,
        score=1.0,
    )


def test_web_cache_basic_get_put() -> None:
    cache = WebRetrievalCache(max_entries=2, ttl_seconds=60)
    policy = WebRetrievalPolicy(allow_external_query=True)
    cands = (_make_candidate("c1"),)

    assert cache.get("web", "query1", policy) is None
    cache.put("web", "query1", policy, cands)

    cached = cache.get("web", "query1", policy)
    assert cached == cands


def test_web_cache_ttl_expiry() -> None:
    curr_time = 100.0

    def time_fn() -> float:
        return curr_time

    cache = WebRetrievalCache(max_entries=2, ttl_seconds=10, time_fn=time_fn)
    policy = WebRetrievalPolicy(allow_external_query=True)
    cands = (_make_candidate("c1"),)

    cache.put("web", "query1", policy, cands)
    assert cache.get("web", "query1", policy) == cands

    # Advance time past TTL
    curr_time = 111.0
    assert cache.get("web", "query1", policy) is None


def test_web_cache_lru_eviction() -> None:
    cache = WebRetrievalCache(max_entries=2, ttl_seconds=60)
    policy = WebRetrievalPolicy(allow_external_query=True)

    cache.put("web", "q1", policy, (_make_candidate("c1"),))
    cache.put("web", "q2", policy, (_make_candidate("c2"),))
    # Access q1 to make q2 oldest
    cache.get("web", "q1", policy)

    # Insert q3, evicts q2
    cache.put("web", "q3", policy, (_make_candidate("c3"),))

    assert cache.get("web", "q1", policy) is not None
    assert cache.get("web", "q2", policy) is None
    assert cache.get("web", "q3", policy) is not None


def test_web_cache_thread_safety_concurrent_access() -> None:
    """Verify thread safety with concurrent reads, writes, and evictions."""
    cache = WebRetrievalCache(max_entries=8, ttl_seconds=60)
    policy = WebRetrievalPolicy(allow_external_query=True)
    num_threads = 8
    ops_per_thread = 100

    def worker(worker_id: int) -> int:
        successes = 0
        for i in range(ops_per_thread):
            key = f"q_{worker_id}_{i % 16}"
            cand = (_make_candidate(f"cand_{worker_id}_{i}"),)
            cache.put("web", key, policy, cand)
            val = cache.get("web", key, policy)
            if val is not None:
                successes += 1
            if i % 25 == 0:
                cache.clear()
        return successes

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, tid) for tid in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == num_threads
    assert all(r > 0 for r in results)

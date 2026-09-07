"""In-memory bounded TTL cache for LiteBridge web retrieval."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from evidenceops.bridge.contracts import WebRetrievalPolicy
from evidenceops.bridge.ports import RawEvidenceCandidate


@dataclass(frozen=True)
class _CacheEntry:
    candidates: tuple[RawEvidenceCandidate, ...]
    expiry_time: float


class WebRetrievalCache:
    """Bounded, thread-safe, in-memory LRU TTL cache for web candidate batches."""

    def __init__(
        self,
        max_entries: int = 64,
        ttl_seconds: int = 300,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self._max_entries = max(max_entries, 1)
        self._ttl_seconds = max(ttl_seconds, 1)
        self._time_fn = time_fn
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()

    def _make_key(
        self,
        source_id: str,
        query: str,
        policy: WebRetrievalPolicy,
    ) -> str:
        parts = [
            source_id,
            query.strip(),
            str(policy.allow_external_query),
            str(policy.max_search_results),
            str(policy.fetch_pages),
            str(policy.max_page_fetches),
        ]
        return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()

    def get(
        self,
        source_id: str,
        query: str,
        policy: WebRetrievalPolicy,
    ) -> tuple[RawEvidenceCandidate, ...] | None:
        """Return cached candidates if present and unexpired; otherwise None."""
        key = self._make_key(source_id, query, policy)
        entry = self._store.get(key)
        if entry is None:
            return None

        now = self._time_fn()
        if now >= entry.expiry_time:
            self._store.pop(key, None)
            return None

        # Move to end for LRU ordering
        self._store.move_to_end(key)
        return entry.candidates

    def put(
        self,
        source_id: str,
        query: str,
        policy: WebRetrievalPolicy,
        candidates: tuple[RawEvidenceCandidate, ...],
    ) -> None:
        """Store candidates in cache with TTL and enforce max_entries bound."""
        key = self._make_key(source_id, query, policy)
        now = self._time_fn()
        expiry_time = now + self._ttl_seconds

        # Evict oldest if full
        if key not in self._store and len(self._store) >= self._max_entries:
            self._store.popitem(last=False)

        self._store[key] = _CacheEntry(candidates=candidates, expiry_time=expiry_time)
        self._store.move_to_end(key)

    def clear(self) -> None:
        """Clear all entries from cache."""
        self._store.clear()

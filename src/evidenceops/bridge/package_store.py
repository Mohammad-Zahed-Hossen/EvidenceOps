"""Thread-safe, bounded in-memory context package store with server-issued opaque handles."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from evidenceops.bridge.contracts import ContextPackage
from evidenceops.bridge.errors import (
    LiteBridgePackageNotFoundError,
    LiteBridgeValidationError,
)


@dataclass(frozen=True)
class _StoredPackageEntry:
    handle: str
    package: ContextPackage
    created_at: float
    expires_at: float


class InterfacePackageStore:
    """Bounded, thread-safe, TTL-based store returning opaque handles for server-issued packages."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 64) -> None:
        if ttl_seconds <= 0:
            raise LiteBridgeValidationError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise LiteBridgeValidationError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.RLock()
        self._entries: dict[str, _StoredPackageEntry] = {}

    def put(self, package: ContextPackage) -> str:
        """Store an immutable ContextPackage and return a new opaque context_handle."""
        if not isinstance(package, ContextPackage):
            raise LiteBridgeValidationError("package must be a valid ContextPackage")

        now = time.time()
        handle = f"ctx_{secrets.token_urlsafe(24)}"
        entry = _StoredPackageEntry(
            handle=handle,
            package=package,
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )

        with self._lock:
            self._purge_expired_locked(now)
            while len(self._entries) >= self._max_entries:
                # Evict oldest created entry
                oldest_handle = min(self._entries, key=lambda k: self._entries[k].created_at)
                del self._entries[oldest_handle]
            self._entries[handle] = entry

        return handle

    def get(self, context_handle: str) -> ContextPackage:
        """Retrieve a stored ContextPackage by handle, raising if missing or expired."""
        if not isinstance(context_handle, str) or not context_handle:
            raise LiteBridgePackageNotFoundError("Context handle not found or expired")

        now = time.time()
        with self._lock:
            entry = self._entries.get(context_handle)
            if entry is None or now > entry.expires_at:
                if entry is not None:
                    del self._entries[context_handle]
                raise LiteBridgePackageNotFoundError(
                    f"Context handle '{context_handle}' not found or expired"
                )
            return entry.package

    def clear(self) -> None:
        """Clear all stored entries."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """Return count of unexpired stored packages."""
        now = time.time()
        with self._lock:
            self._purge_expired_locked(now)
            return len(self._entries)

    def _purge_expired_locked(self, now: float) -> None:
        expired = [h for h, e in self._entries.items() if now > e.expires_at]
        for h in expired:
            del self._entries[h]

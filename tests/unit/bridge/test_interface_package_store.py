"""Unit tests for the server-issued interface package store."""

from __future__ import annotations

import concurrent.futures
import time

import pytest

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ContextPackage,
    ExecutionProfile,
    PlannerDecision,
    PlannerRoute,
    QueryFeatures,
    RetrievalPolicy,
    StopReason,
)
from evidenceops.bridge.errors import (
    LiteBridgePackageNotFoundError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.package_store import InterfacePackageStore


def _make_dummy_package(package_id: str = "pkg_test_123") -> ContextPackage:
    decision = PlannerDecision(
        route=PlannerRoute.LOCAL,
        selected_source_id="evidenceops_local_docs",
        features=QueryFeatures(
            normalized_length=10,
            token_like_count=2,
            has_freshness_cue=False,
            has_local_reference_cue=True,
            has_explicit_time_reference=False,
        ),
        effective_budget=BudgetPolicy(),
    )
    return ContextPackage(
        package_id=package_id,
        query_hash="hash_123",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=(),
        context_text="test context",
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=12,
        estimated_tokens=3,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
    )


def test_put_returns_opaque_handle_different_from_package_id() -> None:
    store = InterfacePackageStore(ttl_seconds=300, max_entries=10)
    pkg = _make_dummy_package("sha256_deterministic_id_123")

    handle = store.put(pkg)

    assert isinstance(handle, str)
    assert handle.startswith("ctx_")
    assert handle != pkg.package_id
    assert len(handle) >= 20


def test_get_retrieves_stored_package() -> None:
    store = InterfacePackageStore(ttl_seconds=300, max_entries=10)
    pkg = _make_dummy_package("sha256_deterministic_id_123")

    handle = store.put(pkg)
    retrieved = store.get(handle)

    assert retrieved.package_id == pkg.package_id
    assert retrieved.context_text == pkg.context_text


def test_guessed_package_id_cannot_retrieve_stored_package() -> None:
    """A deterministic package ID is not an access-control token and cannot retrieve packages."""
    store = InterfacePackageStore(ttl_seconds=300, max_entries=10)
    pkg = _make_dummy_package("sha256_deterministic_id_123")

    store.put(pkg)

    # Attempting to retrieve by package_id must fail
    with pytest.raises(LiteBridgePackageNotFoundError):
        store.get(pkg.package_id)

    # Random unknown handle must fail
    with pytest.raises(LiteBridgePackageNotFoundError):
        store.get("ctx_unknown_random_handle")


def test_store_rejects_non_context_package() -> None:
    store = InterfacePackageStore(ttl_seconds=300, max_entries=10)
    with pytest.raises(LiteBridgeValidationError):
        store.put("not_a_package")  # type: ignore[arg-type]


def test_ttl_expiry_evicts_package() -> None:
    store = InterfacePackageStore(ttl_seconds=1, max_entries=10)
    pkg = _make_dummy_package()

    handle = store.put(pkg)
    assert store.get(handle).package_id == pkg.package_id

    # Wait for TTL expiry
    time.sleep(1.05)

    with pytest.raises(LiteBridgePackageNotFoundError):
        store.get(handle)


def test_capacity_eviction_removes_oldest() -> None:
    store = InterfacePackageStore(ttl_seconds=300, max_entries=2)
    pkg1 = _make_dummy_package("pkg_1")
    pkg2 = _make_dummy_package("pkg_2")
    pkg3 = _make_dummy_package("pkg_3")

    h1 = store.put(pkg1)
    time.sleep(0.01)
    h2 = store.put(pkg2)
    time.sleep(0.01)
    h3 = store.put(pkg3)

    # Oldest (h1) should be evicted
    with pytest.raises(LiteBridgePackageNotFoundError):
        store.get(h1)

    assert store.get(h2).package_id == "pkg_2"
    assert store.get(h3).package_id == "pkg_3"


def test_concurrent_access_thread_safety() -> None:
    store = InterfacePackageStore(ttl_seconds=300, max_entries=500)
    packages = [_make_dummy_package(f"pkg_{i}") for i in range(100)]
    handles: list[str] = []

    def writer(p: ContextPackage) -> str:
        return store.put(p)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(writer, p) for p in packages]
        handles = [f.result() for f in futures]

    assert len(handles) == 100
    assert len(set(handles)) == 100  # All handles are unique

    def reader(h: str) -> str:
        return store.get(h).package_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        read_futures = [executor.submit(reader, h) for h in handles]
        results = [f.result() for f in read_futures]

    assert len(results) == 100

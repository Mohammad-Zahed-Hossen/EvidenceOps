"""Tests for LiteBridge core service facade and source policy routing."""

from __future__ import annotations

import pytest

from evidenceops.bridge.contracts import (
    ExecutionProfile,
    PrivacyClassification,
    RetrievalPolicy,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
    SourcePolicy,
    StopReason,
)
from evidenceops.bridge.errors import (
    LiteBridgeError,
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
    LiteBridgeSourceError,
    LiteBridgeTimeoutError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import RawEvidenceCandidate, RetrievalBatch
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry


class FakeRetriever:
    def __init__(
        self,
        candidates: tuple[RawEvidenceCandidate, ...] = (),
        reproducibility: tuple[tuple[str, str], ...] = (("adapter_id", "fake"),),
    ) -> None:
        self.candidates = candidates
        self.call_count = 0
        self.last_query = ""
        self.last_policy: RetrievalPolicy | None = None
        self.should_raise: Exception | None = None
        self.reproducibility = reproducibility

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        self.call_count += 1
        self.last_query = query
        self.last_policy = policy
        if self.should_raise is not None:
            raise self.should_raise
        return RetrievalBatch(
            candidates=self.candidates,
            retrieval_calls=1,
            retrieval_route=policy.mode,
            reproducibility=self.reproducibility,
        )


def _make_descriptor(
    source_id: str = "src_a",
    adapter_id: str = "adapter_a",
    enabled: bool = True,
    source_version: str | None = None,
) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        display_name=f"Descriptor for {source_id}",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id=adapter_id,
        enabled=enabled,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=10000,
        timeout_ms=5000,
        max_retries=0,
        source_version=source_version,
    )


def test_prepare_context_invokes_retriever_exactly_once() -> None:
    c1 = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="evidenceops_local_docs",
        document_id="doc1",
        chunk_id="chunk1",
        title="Title 1",
        section="Sec 1",
        source_label="doc1.md",
        text="Sample text content",
        retrieval_route="hybrid",
        rank=1,
        score=0.9,
    )
    fake_retriever = FakeRetriever(candidates=(c1,))
    bridge = LiteBridge(retriever=fake_retriever)

    pkg = bridge.prepare_context("what is the architecture?", policy=RetrievalPolicy())

    assert fake_retriever.call_count == 1
    assert fake_retriever.last_query == "what is the architecture?"
    assert pkg.stop_reason == StopReason.SUCCESS
    assert len(pkg.evidence) == 1
    assert pkg.evidence[0].evidence_id == "c1"
    assert pkg.evidence[0].source_id == "evidenceops_local_docs"


def test_prepare_context_direct_mode_permits_none_or_empty_source_policy() -> None:
    c1 = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="direct_source",
        document_id="doc1",
        text="Sample content",
        retrieval_route="hybrid",
        rank=1,
    )
    fake_retriever = FakeRetriever(candidates=(c1,))
    bridge = LiteBridge(retriever=fake_retriever)

    # With source_policy=None
    pkg1 = bridge.prepare_context("test query", source_policy=None)
    assert len(pkg1.evidence) == 1

    # With empty SourcePolicy()
    pkg2 = bridge.prepare_context("test query", source_policy=SourcePolicy())
    assert len(pkg2.evidence) == 1


def test_prepare_context_direct_mode_rejects_specific_source_id_before_retrieval() -> None:
    fake_retriever = FakeRetriever()
    bridge = LiteBridge(retriever=fake_retriever)

    policy = SourcePolicy(allowed_source_ids=("any_source",))
    with pytest.raises(LiteBridgeSourceError) as exc_info:
        bridge.prepare_context("test query", source_policy=policy)

    assert "direct retriever" in str(exc_info.value)
    assert fake_retriever.call_count == 0


def test_prepare_context_rejects_unsupported_profiles_before_retrieval() -> None:
    fake_retriever = FakeRetriever()
    bridge = LiteBridge(retriever=fake_retriever)

    policy = RetrievalPolicy(execution_profile=ExecutionProfile.HYBRID)
    with pytest.raises(LiteBridgeProfileError):
        bridge.prepare_context("query", policy=policy)

    assert fake_retriever.call_count == 0


def test_prepare_context_rejects_blank_query_before_retrieval() -> None:
    fake_retriever = FakeRetriever()
    bridge = LiteBridge(retriever=fake_retriever)

    with pytest.raises(LiteBridgeValidationError):
        bridge.prepare_context("   \n\t  ")

    assert fake_retriever.call_count == 0


def test_prepare_context_handles_retriever_failure_sanitized() -> None:
    fake_retriever = FakeRetriever()
    fake_retriever.should_raise = RuntimeError("Database connection timed out")
    bridge = LiteBridge(retriever=fake_retriever)

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        bridge.prepare_context("valid query")

    assert fake_retriever.call_count == 1
    assert isinstance(exc_info.value, LiteBridgeError)
    assert exc_info.value.__cause__ is not None


def test_prepare_context_maps_timeout_error_to_sanitized_litebridge_timeout() -> None:
    fake_retriever = FakeRetriever()
    fake_retriever.should_raise = TimeoutError("Connection dead after 5000ms")
    bridge = LiteBridge(retriever=fake_retriever)

    with pytest.raises(LiteBridgeTimeoutError) as exc_info:
        bridge.prepare_context("valid query")

    assert "timed out" in str(exc_info.value).lower()
    assert fake_retriever.call_count == 1


def test_prepare_context_preserves_existing_litebridge_timeout_error_without_wrapping() -> None:
    fake_retriever = FakeRetriever()
    fake_retriever.should_raise = LiteBridgeTimeoutError("Pre-constructed timeout")
    bridge = LiteBridge(retriever=fake_retriever)

    with pytest.raises(LiteBridgeTimeoutError) as exc_info:
        bridge.prepare_context("valid query")

    assert "Pre-constructed timeout" in str(exc_info.value)


def test_registry_mode_calls_only_resolved_retriever() -> None:
    c1 = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="source_one",
        document_id="doc1",
        text="Content 1",
        retrieval_route="hybrid",
        rank=1,
    )
    c2 = RawEvidenceCandidate(
        candidate_id="c2",
        source_id="source_two",
        document_id="doc2",
        text="Content 2",
        retrieval_route="hybrid",
        rank=1,
    )

    r1 = FakeRetriever(candidates=(c1,))
    r2 = FakeRetriever(candidates=(c2,))

    registry = SourceRegistry()
    registry.register(_make_descriptor("source_one"), r1, make_default=True)
    registry.register(_make_descriptor("source_two"), r2, make_default=False)

    bridge = LiteBridge(source_registry=registry)

    # 1. Default resolution (no policy)
    pkg_default = bridge.prepare_context("default query")
    assert r1.call_count == 1
    assert r2.call_count == 0
    assert pkg_default.evidence[0].source_id == "source_one"

    # 2. Explicit source selection
    policy = SourcePolicy(allowed_source_ids=("source_two",))
    pkg_explicit = bridge.prepare_context("query for two", source_policy=policy)
    assert r1.call_count == 1
    assert r2.call_count == 1
    assert pkg_explicit.evidence[0].source_id == "source_two"


def test_registry_mode_rejects_mismatched_candidate_source_id() -> None:
    c_bad = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="wrong_source_id",
        document_id="doc1",
        text="Content 1",
        retrieval_route="hybrid",
        rank=1,
    )
    r = FakeRetriever(candidates=(c_bad,))
    registry = SourceRegistry()
    registry.register(_make_descriptor("expected_source"), r, make_default=True)

    bridge = LiteBridge(source_registry=registry)
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        bridge.prepare_context("test query")

    assert "does not match resolved source" in str(exc_info.value)


def test_registry_mode_rejects_candidate_with_non_local_source_kind() -> None:
    c_non_local = RawEvidenceCandidate.model_construct(
        candidate_id="c1",
        source_kind="web_page",  # type: ignore[arg-type]
        source_id="local_src",
        document_id="doc1",
        text="Content 1",
        retrieval_route="hybrid",
        rank=1,
    )
    r = FakeRetriever(candidates=(c_non_local,))
    registry = SourceRegistry()
    registry.register(_make_descriptor("local_src"), r, make_default=True)

    bridge = LiteBridge(source_registry=registry)
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        bridge.prepare_context("test query")

    assert "not permitted in Phase L2" in str(exc_info.value)


def test_core_generated_reproducibility_cannot_be_overwritten_by_adapter() -> None:
    c1 = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="official_source",
        document_id="doc1",
        text="Content 1",
        retrieval_route="hybrid",
        rank=1,
    )
    # Adapter attempts to inject malicious/conflicting source_id and adapter_id
    hostile_repro = (
        ("source_id", "fake_source_injection"),
        ("adapter_id", "fake_adapter_injection"),
        ("safe_custom_key", "custom_val"),
    )
    r = FakeRetriever(candidates=(c1,), reproducibility=hostile_repro)

    registry = SourceRegistry()
    registry.register(
        _make_descriptor(source_id="official_source", adapter_id="official_adapter"),
        r,
        make_default=True,
    )

    bridge = LiteBridge(source_registry=registry)
    pkg = bridge.prepare_context("query")

    repro_dict = dict(pkg.reproducibility)
    # The official core descriptor values must win!
    assert repro_dict["source_id"] == "official_source"
    assert repro_dict["adapter_id"] == "official_adapter"
    assert repro_dict["safe_custom_key"] == "custom_val"


def test_package_id_changes_when_source_changes_and_is_timing_independent() -> None:
    c1 = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="source_a",
        document_id="doc1",
        text="Identical content",
        retrieval_route="hybrid",
        rank=1,
    )
    c2 = RawEvidenceCandidate(
        candidate_id="c1",
        source_id="source_b",
        document_id="doc1",
        text="Identical content",
        retrieval_route="hybrid",
        rank=1,
    )

    r1 = FakeRetriever(candidates=(c1,))
    r2 = FakeRetriever(candidates=(c2,))

    registry = SourceRegistry()
    registry.register(_make_descriptor("source_a", adapter_id="ad_a"), r1, make_default=True)
    registry.register(_make_descriptor("source_b", adapter_id="ad_b"), r2, make_default=False)

    bridge = LiteBridge(source_registry=registry)

    pkg_a1 = bridge.prepare_context(
        "query", source_policy=SourcePolicy(allowed_source_ids=("source_a",))
    )
    pkg_a2 = bridge.prepare_context(
        "query", source_policy=SourcePolicy(allowed_source_ids=("source_a",))
    )
    pkg_b = bridge.prepare_context(
        "query", source_policy=SourcePolicy(allowed_source_ids=("source_b",))
    )

    # Stable for identical inputs
    assert pkg_a1.package_id == pkg_a2.package_id
    # Changes when source identity changes
    assert pkg_a1.package_id != pkg_b.package_id

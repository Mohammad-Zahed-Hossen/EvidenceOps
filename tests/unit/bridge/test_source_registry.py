"""Tests for LiteBridge Phase L2 SourceRegistry."""

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
)
from evidenceops.bridge.errors import (
    LiteBridgeProfileError,
    LiteBridgeSourceError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import EvidenceRetriever, RetrievalBatch
from evidenceops.bridge.source_registry import SourceRegistry


class DummyRetriever(EvidenceRetriever):
    def __init__(self) -> None:
        self.retrieve_called = False

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        self.retrieve_called = True
        return RetrievalBatch()


def _make_descriptor(
    source_id: str = "test_source",
    enabled: bool = True,
) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        display_name=f"Display for {source_id}",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id="test_adapter",
        enabled=enabled,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=1000,
        timeout_ms=1000,
        max_retries=0,
    )


def test_registry_registers_and_resolves_default_source() -> None:
    registry = SourceRegistry()
    desc = _make_descriptor("default_source")
    retriever = DummyRetriever()

    registry.register(desc, retriever, make_default=True)

    # Resolve with None
    resolved_desc, resolved_retriever = registry.resolve(None, ExecutionProfile.LOCAL_ONLY)
    assert resolved_desc.source_id == "default_source"
    assert resolved_retriever is retriever
    assert not retriever.retrieve_called

    # Resolve with empty policy
    resolved_desc2, resolved_retriever2 = registry.resolve(
        SourcePolicy(), ExecutionProfile.LOCAL_ONLY
    )
    assert resolved_desc2.source_id == "default_source"
    assert resolved_retriever2 is retriever
    assert not retriever.retrieve_called


def test_registry_resolves_explicitly_allowed_source() -> None:
    registry = SourceRegistry()
    desc1 = _make_descriptor("default_source")
    retriever1 = DummyRetriever()
    registry.register(desc1, retriever1, make_default=True)

    desc2 = _make_descriptor("secondary_source")
    retriever2 = DummyRetriever()
    registry.register(desc2, retriever2, make_default=False)

    policy = SourcePolicy(allowed_source_ids=("secondary_source",))
    resolved_desc, resolved_retriever = registry.resolve(policy, ExecutionProfile.LOCAL_ONLY)

    assert resolved_desc.source_id == "secondary_source"
    assert resolved_retriever is retriever2
    assert not retriever1.retrieve_called
    assert not retriever2.retrieve_called


def test_registry_rejects_duplicate_registration() -> None:
    registry = SourceRegistry()
    desc1 = _make_descriptor("same_id")
    desc2 = _make_descriptor("same_id")

    registry.register(desc1, DummyRetriever())
    with pytest.raises(LiteBridgeSourceError) as exc_info:
        registry.register(desc2, DummyRetriever())

    assert "already registered" in str(exc_info.value)
    assert "same_id" in str(exc_info.value)


def test_registry_rejects_unknown_source_before_retrieval() -> None:
    registry = SourceRegistry()
    desc = _make_descriptor("default_source")
    retriever = DummyRetriever()
    registry.register(desc, retriever, make_default=True)

    policy = SourcePolicy(allowed_source_ids=("non_existent_source",))
    with pytest.raises(LiteBridgeSourceError) as exc_info:
        registry.resolve(policy, ExecutionProfile.LOCAL_ONLY)

    assert "non_existent_source" in str(exc_info.value)
    assert not retriever.retrieve_called


def test_registry_rejects_disabled_source_before_retrieval() -> None:
    registry = SourceRegistry()
    desc = _make_descriptor("disabled_source", enabled=False)
    retriever = DummyRetriever()
    registry.register(desc, retriever, make_default=True)

    with pytest.raises(LiteBridgeSourceError) as exc_info:
        registry.resolve(None, ExecutionProfile.LOCAL_ONLY)

    assert "disabled" in str(exc_info.value)
    assert "disabled_source" in str(exc_info.value)
    assert not retriever.retrieve_called


def test_registry_rejects_non_local_only_profile_before_retrieval() -> None:
    registry = SourceRegistry()
    desc = _make_descriptor("default_source")
    retriever = DummyRetriever()
    registry.register(desc, retriever, make_default=True)

    with pytest.raises(LiteBridgeProfileError) as exc_info:
        registry.resolve(None, ExecutionProfile.HYBRID)

    assert "hybrid" in str(exc_info.value)
    assert not retriever.retrieve_called


def test_registry_rejects_multiple_sources_before_retrieval() -> None:
    registry = SourceRegistry()
    desc = _make_descriptor("default_source")
    retriever = DummyRetriever()
    registry.register(desc, retriever, make_default=True)

    with pytest.raises(LiteBridgeValidationError):
        registry.resolve(  # type: ignore[arg-type]
            SourcePolicy.model_construct(allowed_source_ids=("s1", "s2")),
            ExecutionProfile.LOCAL_ONLY,
        )
    assert not retriever.retrieve_called


def test_registry_error_sanitization_does_not_leak_internals() -> None:
    registry = SourceRegistry()
    # No default source registered
    with pytest.raises(LiteBridgeSourceError) as exc_info:
        registry.resolve(None, ExecutionProfile.LOCAL_ONLY)
    msg = str(exc_info.value)
    assert "default" in msg.lower()
    assert "/" not in msg
    assert "\\" not in msg

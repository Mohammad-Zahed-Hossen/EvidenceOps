"""Tests for LiteBridge core service facade."""

from __future__ import annotations

import pytest

from evidenceops.bridge.contracts import ExecutionProfile, RetrievalPolicy, StopReason
from evidenceops.bridge.errors import (
    LiteBridgeError,
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import RawEvidenceCandidate, RetrievalBatch
from evidenceops.bridge.service import LiteBridge


class FakeRetriever:
    def __init__(self, candidates: tuple[RawEvidenceCandidate, ...] = ()) -> None:
        self.candidates = candidates
        self.call_count = 0
        self.last_query = ""
        self.last_policy: RetrievalPolicy | None = None
        self.should_raise: Exception | None = None

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
            reproducibility=(("adapter_id", "fake"),),
        )


def test_prepare_context_invokes_retriever_exactly_once() -> None:
    c1 = RawEvidenceCandidate(
        candidate_id="c1",
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
    # Check that it inherits from LiteBridgeError and preserves cause internally
    assert isinstance(exc_info.value, LiteBridgeError)
    assert exc_info.value.__cause__ is not None

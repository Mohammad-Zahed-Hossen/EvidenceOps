"""Unit tests for EvidenceOpsState guardrails, bounds, and terminal invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import AbstentionReason, Action, QueryRoute, RunStatus
from evidenceops.domain.models import EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState, QueryFeatures


def test_valid_initial_state() -> None:
    state = EvidenceOpsState(
        run_id="run-1",
        original_query="What is FastAPI?",
        active_query="What is FastAPI?",
    )
    assert state.run_id == "run-1"
    assert state.status == RunStatus.CREATED
    assert state.original_query == "What is FastAPI?"
    assert state.active_query == "What is FastAPI?"
    assert state.iteration_count == 0
    assert state.retrieval_calls == 0
    assert state.max_iterations == 3
    assert state.max_retrieval_calls == 3
    assert state.max_context_chars == 24000
    assert state.evidence == []
    assert state.citations == []


def test_blank_and_whitespace_query_rejection() -> None:
    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run-1", original_query="", active_query="valid")

    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run-1", original_query="   ", active_query="valid")

    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run-1", original_query="valid", active_query="")

    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run-1", original_query="valid", active_query="   \t\n")


def test_oversized_query_rejection() -> None:
    oversized = "a" * 1001
    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run-1", original_query=oversized, active_query="valid")

    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run-1", original_query="valid", active_query=oversized)


def test_iteration_and_retrieval_bounds_enforcement() -> None:
    # Cannot exceed 3
    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            max_iterations=4,
        )

    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            max_retrieval_calls=4,
        )

    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            iteration_count=4,
        )

    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            retrieval_calls=4,
        )


def test_non_finite_score_rejection() -> None:
    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            sufficiency_score=float("nan"),
        )

    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            conflict_score=float("inf"),
        )


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="run-1",
            original_query="q",
            active_query="q",
            unexpected_field="disallowed",  # type: ignore[call-arg]
        )


def test_terminal_state_completed_requires_answer() -> None:
    # COMPLETED requires non-empty answer
    with pytest.raises(ValidationError, match="completed.*answer"):
        EvidenceOpsState(
            run_id="run-1",
            status=RunStatus.COMPLETED,
            original_query="q",
            active_query="q",
            answer=None,
        )

    with pytest.raises(ValidationError, match="completed.*answer"):
        EvidenceOpsState(
            run_id="run-1",
            status=RunStatus.COMPLETED,
            original_query="q",
            active_query="q",
            answer="   ",
        )

    valid_completed = EvidenceOpsState(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        original_query="q",
        active_query="q",
        answer="Valid grounded answer [C1].",
        citations=["C1"],
    )
    assert valid_completed.status == RunStatus.COMPLETED


def test_terminal_state_abstained_requires_reason() -> None:
    with pytest.raises(ValidationError, match="abstained.*reason"):
        EvidenceOpsState(
            run_id="run-1",
            status=RunStatus.ABSTAINED,
            original_query="q",
            active_query="q",
            abstention_reason=None,
        )

    valid_abstained = EvidenceOpsState(
        run_id="run-1",
        status=RunStatus.ABSTAINED,
        original_query="q",
        active_query="q",
        abstention_reason=AbstentionReason.EVIDENCE_BELOW_THRESHOLD,
    )
    assert valid_abstained.status == RunStatus.ABSTAINED
    assert valid_abstained.abstention_reason == "evidence_below_threshold"


def test_dict_conversion_roundtrip() -> None:
    state = EvidenceOpsState(
        run_id="run-roundtrip",
        original_query="How to run BM25?",
        active_query="How to run BM25?",
        route=QueryRoute.SPARSE,
        next_action=Action.RETRIEVE_SPARSE,
        iteration_count=1,
        retrieval_calls=1,
        query_features=QueryFeatures(has_code_terms=True),
        evidence=[
            EvidenceRecord(
                chunk_id="chunk-1",
                document_id="doc-1",
                title="BM25",
                source_uri="docs/bm25.md",
                text="BM25 index text",
                retrieval_method="sparse",
                retrieval_rank=1,
                retrieval_score=2.5,
                citation_id="C1",
            )
        ],
    )
    d = state.to_langgraph_dict()
    restored = EvidenceOpsState.from_langgraph_dict(d)
    assert restored.run_id == state.run_id
    assert restored.iteration_count == 1
    assert restored.evidence[0].chunk_id == "chunk-1"
    assert restored.evidence[0].citation_id == "C1"

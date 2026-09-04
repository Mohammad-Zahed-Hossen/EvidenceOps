"""Unit tests for conditional edge routing in LangGraph workflow."""

from __future__ import annotations

from evidenceops.domain.enums import Action, EvidenceStatus
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.graph.routing import (
    route_after_citation_validation,
    route_after_decision,
    route_after_evaluation,
)


def test_route_after_decision_direct_answer() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="hi",
        active_query="hi",
        next_action=Action.DIRECT_ANSWER,
    )
    dest = route_after_decision(state.to_langgraph_dict())
    assert dest == "generate"


def test_route_after_decision_retrieve() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        next_action=Action.RETRIEVE_SPARSE,
    )
    dest = route_after_decision(state.to_langgraph_dict())
    assert dest == "retrieve"


def test_route_after_decision_abstain() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        next_action=Action.ABSTAIN,
    )
    dest = route_after_decision(state.to_langgraph_dict())
    assert dest == "abstain"


def test_route_after_evaluation_sufficient() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        evidence_status=EvidenceStatus.SUFFICIENT,
        conflict_score=0.0,
    )
    dest = route_after_evaluation(state.to_langgraph_dict())
    assert dest == "generate"


def test_route_after_evaluation_uncertain_with_budget() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        evidence_status=EvidenceStatus.INSUFFICIENT,
        iteration_count=1,
        retrieval_calls=1,
        max_iterations=3,
        max_retrieval_calls=3,
    )
    dest = route_after_evaluation(state.to_langgraph_dict())
    assert dest == "reformulate"


def test_route_after_evaluation_budget_exhausted() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        evidence_status=EvidenceStatus.INSUFFICIENT,
        iteration_count=3,
        retrieval_calls=3,
        max_iterations=3,
        max_retrieval_calls=3,
    )
    dest = route_after_evaluation(state.to_langgraph_dict())
    assert dest == "abstain"


def test_route_after_citation_validation_valid() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        answer="Valid [C1].",
        citations=["C1"],
        metadata={"citation_validation_failed": False},
    )
    dest = route_after_citation_validation(state.to_langgraph_dict())
    assert dest == "finalize"


def test_route_after_citation_validation_retry() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        metadata={"citation_validation_failed": True, "generation_attempts": 1},
    )
    dest = route_after_citation_validation(state.to_langgraph_dict())
    assert dest == "generate"


def test_route_after_citation_validation_exhausted() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        metadata={"citation_validation_failed": True, "generation_attempts": 2},
    )
    dest = route_after_citation_validation(state.to_langgraph_dict())
    assert dest == "abstain"

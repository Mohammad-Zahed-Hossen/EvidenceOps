"""Unit tests for the deterministic heuristic retrieval controller."""

from __future__ import annotations

import pytest

from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.controller.heuristic import HeuristicRetrievalController
from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute
from evidenceops.domain.state import EvidenceOpsState


@pytest.fixture
def controller() -> HeuristicRetrievalController:
    return HeuristicRetrievalController(feature_extractor=RegexFeatureExtractor())


def test_exact_identifier_routes_to_sparse(controller: HeuristicRetrievalController) -> None:
    state = EvidenceOpsState(
        run_id="run-1",
        original_query="What does the --max-tokens CLI flag do in Ollama?",
        active_query="What does the --max-tokens CLI flag do in Ollama?",
    )
    decision = controller.decide(state)
    assert decision.action == Action.RETRIEVE_SPARSE
    assert decision.route == QueryRoute.SPARSE
    assert "sparse" in decision.reason_code


def test_conceptual_question_routes_to_dense(controller: HeuristicRetrievalController) -> None:
    state = EvidenceOpsState(
        run_id="run-2",
        original_query="Explain the concept of semantic vector representations",
        active_query="Explain the concept of semantic vector representations",
    )
    decision = controller.decide(state)
    assert decision.action == Action.RETRIEVE_DENSE
    assert decision.route == QueryRoute.DENSE
    assert "dense" in decision.reason_code


def test_comparison_routes_to_hybrid(controller: HeuristicRetrievalController) -> None:
    state = EvidenceOpsState(
        run_id="run-3",
        original_query="Compare sparse retrieval vs dense retrieval in Qdrant",
        active_query="Compare sparse retrieval vs dense retrieval in Qdrant",
    )
    decision = controller.decide(state)
    assert decision.action == Action.RETRIEVE_HYBRID
    assert decision.route == QueryRoute.HYBRID
    assert "hybrid" in decision.reason_code


def test_greeting_allows_direct_answer_when_no_citation_required(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-4",
        original_query="Hello! Good morning.",
        active_query="Hello! Good morning.",
        metadata={"require_citations": False},
    )
    decision = controller.decide(state)
    assert decision.action == Action.DIRECT_ANSWER
    assert decision.route == QueryRoute.DIRECT
    assert "direct" in decision.reason_code


def test_factual_query_never_routes_to_direct_answer(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-5",
        original_query="What is the default port for Qdrant vector database?",
        active_query="What is the default port for Qdrant vector database?",
        metadata={"require_citations": False},
    )
    decision = controller.decide(state)
    assert decision.action != Action.DIRECT_ANSWER


def test_sufficient_evidence_stops_and_generates(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-6",
        original_query="How to create a Qdrant collection?",
        active_query="How to create a Qdrant collection?",
        retrieval_calls=1,
        iteration_count=1,
        evidence_status=EvidenceStatus.SUFFICIENT,
        sufficiency_score=0.85,
        conflict_score=0.0,
    )
    decision = controller.decide(state)
    assert decision.action == Action.STOP
    assert "sufficient" in decision.reason_code


def test_uncertain_evidence_with_budget_triggers_reformulation(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-7",
        original_query="How to create a Qdrant collection?",
        active_query="How to create a Qdrant collection?",
        retrieval_calls=1,
        iteration_count=0,
        evidence_status=EvidenceStatus.INSUFFICIENT,
        sufficiency_score=0.45,
        conflict_score=0.0,
        max_iterations=3,
    )
    decision = controller.decide(state)
    assert decision.action == Action.REFORMULATE
    assert "reformulate" in decision.reason_code


def test_conflicting_evidence_triggers_alternative_route_if_available(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-8",
        original_query="Is FastAPI async by default?",
        active_query="Is FastAPI async by default?",
        route=QueryRoute.DENSE,
        retrieval_calls=1,
        iteration_count=1,
        evidence_status=EvidenceStatus.CONFLICTING,
        conflict_score=0.75,
    )
    decision = controller.decide(state)
    # Should attempt alternate route (e.g. SPARSE or HYBRID)
    assert decision.action in (Action.RETRIEVE_SPARSE, Action.RETRIEVE_HYBRID)


def test_budget_exhaustion_triggers_abstention(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-9",
        original_query="Unknown obscure query",
        active_query="Unknown obscure query",
        retrieval_calls=3,
        iteration_count=3,
        max_retrieval_calls=3,
        max_iterations=3,
        evidence_status=EvidenceStatus.INSUFFICIENT,
        sufficiency_score=0.20,
    )
    decision = controller.decide(state)
    assert decision.action == Action.ABSTAIN
    assert "budget" in decision.reason_code


def test_deterministic_repeated_decisions(
    controller: HeuristicRetrievalController,
) -> None:
    state = EvidenceOpsState(
        run_id="run-10",
        original_query="Compare FastEmbed vs FlashRank",
        active_query="Compare FastEmbed vs FlashRank",
    )
    d1 = controller.decide(state)
    d2 = controller.decide(state)
    assert d1.model_dump() == d2.model_dump()

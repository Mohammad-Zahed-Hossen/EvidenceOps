"""Conditional edge routing for EvidenceOps LangGraph workflow."""

from __future__ import annotations

from typing import Any

from evidenceops.domain.enums import Action, EvidenceStatus, RunStatus


def route_after_decision(state: dict[str, Any]) -> str:
    """Route execution after controller decision.

    Returns:
        "generate": For direct answer or stop (sufficient evidence) actions.
        "retrieve": For retrieval actions (sparse, dense, hybrid).
        "reformulate": For reformulation actions.
        "abstain": For abstention decisions.
    """
    next_action = state.get("next_action")
    if next_action in (Action.DIRECT_ANSWER, "direct_answer", Action.STOP, "stop"):
        return "generate"
    if next_action in (
        Action.RETRIEVE_SPARSE,
        Action.RETRIEVE_DENSE,
        Action.RETRIEVE_HYBRID,
        "retrieve_sparse",
        "retrieve_dense",
        "retrieve_hybrid",
    ):
        return "retrieve"
    if next_action in (Action.REFORMULATE, "reformulate"):
        return "reformulate"
    if next_action in (Action.ABSTAIN, "abstain"):
        return "abstain"
    return "abstain"


def route_after_evaluation(state: dict[str, Any]) -> str:
    """Route execution after evidence sufficiency and conflict evaluation.

    Returns:
        "generate": When evidence is sufficient and free of blocking conflict.
        "reformulate": When evidence is insufficient/uncertain but budget remains.
        "abstain": When evidence is insufficient/conflicting and budget is exhausted.
    """
    status = state.get("evidence_status")
    if status in (EvidenceStatus.SUFFICIENT, "sufficient"):
        return "generate"

    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)
    retrieval_calls = state.get("retrieval_calls", 0)
    max_retrieval_calls = state.get("max_retrieval_calls", 3)

    if iteration_count < max_iterations and retrieval_calls < max_retrieval_calls:
        return "reformulate"

    return "abstain"


def route_after_citation_validation(state: dict[str, Any]) -> str:
    """Route execution after inline citation validation.

    Returns:
        "finalize": Citations are valid and complete.
        "generate": Citation validation failed and retry budget remains (< 2).
        "abstain": Citation validation failed after retry attempt or run already abstained.
    """
    if state.get("status") in (RunStatus.ABSTAINED, "abstained"):
        return "abstain"

    metadata = state.get("metadata", {})
    failed = metadata.get("citation_validation_failed", False)
    if not failed:
        return "finalize"

    attempts = metadata.get("generation_attempts", 1)
    if attempts < 2:
        return "generate"

    return "abstain"

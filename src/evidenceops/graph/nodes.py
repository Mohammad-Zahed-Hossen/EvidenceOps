"""Individual orchestration node functions for LangGraph workflow."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from evidenceops.controller.contracts import FeatureExtractor, RetrievalController
from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.controller.heuristic import HeuristicRetrievalController
from evidenceops.domain.enums import AbstentionReason, Action, EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.evidence.adapter import adapt_retrieval_results
from evidenceops.evidence.citations import validate_answer_citations
from evidenceops.evidence.conflict import detect_evidence_conflicts
from evidenceops.evidence.context import pack_evidence_context
from evidenceops.evidence.sufficiency import evaluate_sufficiency
from evidenceops.generation.contracts import GeneratorClient, QueryReformulator
from evidenceops.generation.prompts import (
    build_citation_correction_prompt,
    build_direct_answer_prompt,
    build_grounded_prompt,
)
from evidenceops.generation.reformulator import LocalQueryReformulator
from evidenceops.retrieval.contracts import Reranker, RetrievalResult, SparseRetriever


def validated_node(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Validate both sides of every node, including calls outside the compiled graph."""

    @wraps(function)
    def boundary(state: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        validated = EvidenceOpsState.from_langgraph_dict(state).to_langgraph_dict()
        result = function(validated, *args, **kwargs)
        return EvidenceOpsState.from_langgraph_dict(result).to_langgraph_dict()

    return boundary


@validated_node
def initialize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Initialize workflow state with running status."""
    updated = dict(state)
    updated["status"] = RunStatus.RUNNING
    return updated


@validated_node
def extract_features_node(
    state: dict[str, Any],
    extractor: FeatureExtractor | None = None,
) -> dict[str, Any]:
    """Extract syntactic, structural, and domain features from active query."""
    updated = dict(state)
    active_extractor = extractor or RegexFeatureExtractor()
    query = str(updated.get("active_query", updated.get("original_query", "")))
    features = active_extractor.extract(query)
    updated["query_features"] = features.model_dump(mode="python")
    return updated


@validated_node
def controller_decide_node(
    state: dict[str, Any],
    controller: RetrievalController | None = None,
) -> dict[str, Any]:
    """Apply deterministic heuristic controller rules to select the next action."""
    updated = dict(state)
    if updated["abstention_reason"]:
        return updated
    active_controller = controller or HeuristicRetrievalController()
    state_obj = EvidenceOpsState.from_langgraph_dict(updated)
    decision = active_controller.decide(state_obj)

    updated["next_action"] = decision.action
    if decision.route is not None:
        updated["route"] = decision.route
    if decision.action == Action.ABSTAIN:
        updated["abstention_reason"] = decision.reason_code
    metadata = updated.setdefault("metadata", {})
    metadata["decision_reason_code"] = decision.reason_code
    return updated


@validated_node
def retrieve_node(
    state: dict[str, Any],
    sparse_retriever: SparseRetriever | None = None,
    dense_retriever: SparseRetriever | None = None,
    hybrid_retriever: SparseRetriever | None = None,
) -> dict[str, Any]:
    """Execute the selected public call, or select one explicit local fallback."""
    updated = state
    if updated["abstention_reason"]:
        return updated
    if updated["retrieval_calls"] >= updated["max_retrieval_calls"]:
        return abstain_node(updated, "retrieval_budget_exhausted")
    if updated["iteration_count"] >= updated["max_iterations"]:
        return abstain_node(updated, "iteration_budget_exhausted")
    query, route = updated["active_query"], updated["route"]
    if any(a["query"] == query and a["route"] == route for a in updated["attempts"]):
        return abstain_node(updated, "repeated_query_route")
    retrievers = {
        QueryRoute.SPARSE: sparse_retriever,
        QueryRoute.DENSE: dense_retriever,
        QueryRoute.HYBRID: hybrid_retriever,
    }
    retriever = retrievers.get(route)
    metadata = updated["metadata"]
    metadata["fallback_pending"] = False
    metadata["refinement_ready"] = False
    start = time.perf_counter()
    raw_results: tuple[RetrievalResult, ...] = ()
    error = None
    try:
        if retriever is None:
            raise ValueError("route unavailable")
        updated["retrieval_calls"] += 1
        raw_results = tuple(
            RetrievalResult.model_validate(r.model_dump())
            for r in retriever.search(query, limit=20)
        )[:20]
        new_evidence = adapt_retrieval_results(raw_results)
    except Exception:
        error = "retrieval_unavailable"
        new_evidence = ()
    elapsed = (time.perf_counter() - start) * 1000
    actions = {
        QueryRoute.SPARSE: Action.RETRIEVE_SPARSE,
        QueryRoute.DENSE: Action.RETRIEVE_DENSE,
        QueryRoute.HYBRID: Action.RETRIEVE_HYBRID,
    }
    updated["attempts"].append(
        dict(
            action=actions.get(route, Action.ABSTAIN),
            query=query,
            route=route,
            candidates_returned=len(raw_results),
            accepted_evidence=len(new_evidence),
            latency_ms=elapsed,
            cache_hit=False,
            error=error,
        )
    )
    if error:
        metadata.setdefault("failures", []).append({"stage": "retrieval", "code": error})
        tried = {a["route"] for a in updated["attempts"]}
        fallback = next(
            (r for r, dep in retrievers.items() if dep is not None and r not in tried), None
        )
        if (
            fallback is not None
            and not metadata.get("fallback_used")
            and updated["retrieval_calls"] < updated["max_retrieval_calls"]
        ):
            metadata.update(
                fallback_used=True,
                fallback_pending=True,
                decision_reason_code="local_failure_fallback",
            )
            updated["route"] = fallback
            updated["next_action"] = actions[fallback]
            return updated
        return abstain_node(updated, "retrieval_unavailable")
    previous_ids = set(metadata.get("last_evidence_ids", []))
    new_ids = {e.chunk_id for e in new_evidence}
    if metadata.get("retrieval_succeeded") and new_ids == previous_ids:
        reason = (
            "conflicting_evidence" if updated["conflict_score"] >= 0.60 else "unchanged_evidence"
        )
        return abstain_node(updated, reason)
    metadata.update(last_evidence_ids=sorted(new_ids), retrieval_succeeded=True)
    metadata.pop("packed_context", None)
    metadata["context_characters"] = 0
    metadata["raw_candidates"] = [r.model_dump() for r in raw_results]
    updated["evidence"] = [e.model_dump() for e in new_evidence]
    # Inspect all retrieved candidates before reranking can discard a witness.
    conflict = detect_evidence_conflicts(new_evidence)
    metadata["conflicting_pairs"] = sorted(
        set(tuple(p) for p in metadata.get("conflicting_pairs", []) + conflict.conflicting_pairs)
    )
    updated["conflict_score"] = max(updated["conflict_score"], conflict.conflict_score)
    if updated["conflict_score"] >= metadata.get("conflict_threshold", 0.60):
        updated["evidence_status"] = EvidenceStatus.CONFLICTING
        return abstain_node(updated, "conflicting_evidence")
    return updated


@validated_node
def rerank_node(state: dict[str, Any], reranker: Reranker | None = None) -> dict[str, Any]:
    """Invoke Phase 1C reranking, retaining original route, rank and score."""
    if state["abstention_reason"] or state["metadata"].get("fallback_pending"):
        return state
    if reranker is None or not state["evidence"]:
        return state
    try:
        candidates = tuple(
            RetrievalResult.model_validate(r) for r in state["metadata"].get("raw_candidates", [])
        )[:20]
        if not candidates:
            raise ValueError("missing complete candidates")
        by_id = {e["chunk_id"]: e for e in state["evidence"]}
        originals = {r.chunk_id: r for r in candidates}
        ranked = reranker.rerank(
            state["original_query"], candidates, limit=state["metadata"].get("top_k_context", 6)
        )
        if not ranked or len(ranked) > 6 or len({r.chunk_id for r in ranked}) != len(ranked):
            raise ValueError("invalid reranker cardinality")
        evidence = []
        for item in ranked:
            if item.chunk_id not in originals or item.chunk != originals[item.chunk_id].chunk:
                raise ValueError("invalid reranker identity")
            score = float(item.metadata["rerank_score"])
            if not math.isfinite(score):
                raise ValueError("nonfinite reranker score")
            record = dict(by_id[item.chunk_id])
            record["rerank_score"] = score
            evidence.append(record)
        evidence.sort(key=lambda e: (-e["rerank_score"], e["retrieval_rank"], e["chunk_id"]))
        state["evidence"] = evidence
        state["metadata"]["reranker_executed"] = True
        return state
    except Exception:
        state["metadata"].setdefault("failures", []).append(
            {"stage": "rerank", "code": "reranker_unavailable"}
        )
        return abstain_node(state, "reranker_unavailable")


@validated_node
def evaluate_evidence_node(state: dict[str, Any]) -> dict[str, Any]:
    """Evaluate only bounded generator context; preserve material conflict witnesses."""
    if state["abstention_reason"] or state["metadata"].get("fallback_pending"):
        return state
    metadata = state["metadata"]
    records = [EvidenceRecord.model_validate(e) for e in state["evidence"]]
    conflict = detect_evidence_conflicts(records)
    metadata["conflicting_pairs"] = sorted(
        set(tuple(p) for p in metadata.get("conflicting_pairs", []) + conflict.conflicting_pairs)
    )
    state["conflict_score"] = max(state["conflict_score"], conflict.conflict_score)
    if state["conflict_score"] >= metadata.get("conflict_threshold", 0.60):
        state["evidence_status"] = EvidenceStatus.CONFLICTING
        # SSOT permits abstention OR one independent route. Conservative abstention
        # retains witnesses instead of allowing a retry to erase contradictory claims.
        return abstain_node(state, "conflicting_evidence")
    packed = pack_evidence_context(
        records,
        max_chunks=metadata.get("top_k_context", 6),
        max_characters=state["max_context_chars"],
    )
    state["evidence"] = [e.model_dump() for e in packed.selected_evidence]
    metadata["packed_context"] = packed.formatted_context
    metadata["context_characters"] = packed.total_characters
    result = evaluate_sufficiency(
        state["original_query"],
        packed.selected_evidence,
        sufficient_threshold=metadata.get("sufficiency_threshold", 0.72),
        insufficient_threshold=metadata.get("abstain_threshold", 0.35),
    )
    metadata["sufficiency_components"] = result.model_dump(mode="json")
    state["sufficiency_score"] = result.composite_score
    state["evidence_status"] = result.status
    return state


@validated_node
def reformulate_node(
    state: dict[str, Any], reformulator: QueryReformulator | None = None
) -> dict[str, Any]:
    """Count a successful distinct reformulation once; failed refinement terminates."""
    if state["abstention_reason"]:
        return state
    if state["retrieval_calls"] >= state["max_retrieval_calls"]:
        return abstain_node(state, "retrieval_budget_exhausted")
    if state["iteration_count"] >= state["max_iterations"]:
        return abstain_node(state, "iteration_budget_exhausted")
    previous = [a["query"] for a in state["attempts"]] + [
        state["original_query"],
        state["active_query"],
    ]

    def normalize(query: str) -> str:
        return " ".join(query.casefold().split())

    try:
        query = (reformulator or LocalQueryReformulator()).reformulate(
            state["active_query"], previous_queries=previous
        )
        if (
            not query.strip()
            or len(query) > 1000
            or normalize(query) in {normalize(q) for q in previous}
        ):
            raise ValueError("invalid or duplicate refinement")
    except Exception:
        return abstain_node(state, "duplicate_reformulation")
    state["active_query"] = query
    state["metadata"]["refinement_ready"] = True
    state["iteration_count"] += 1
    # A completed refinement must leave room for its retrieval under the SSOT guardrail.
    if state["iteration_count"] >= state["max_iterations"]:
        return abstain_node(state, "iteration_budget_exhausted")
    return state


@validated_node
def generate_node(
    state: dict[str, Any], generator_client: GeneratorClient | None = None
) -> dict[str, Any]:
    """Generate only with accepted context or an independently verified greeting gate."""
    if state["abstention_reason"]:
        return abstain_node(state)
    metadata = state["metadata"]
    direct = (
        state["next_action"] == Action.DIRECT_ANSWER
        and not metadata.get("require_citations", True)
        and RegexFeatureExtractor()
        .extract(state["original_query"])
        .predicted_external_knowledge_probability
        < 0.20
    )
    records = [EvidenceRecord.model_validate(e) for e in state["evidence"]]
    if not direct and (not records or state["conflict_score"] >= 0.30):
        return abstain_node(
            state,
            "conflicting_evidence"
            if state["conflict_score"] >= 0.30
            else "evidence_below_threshold",
        )
    if not direct and (
        state["evidence_status"] != EvidenceStatus.SUFFICIENT
        or state["sufficiency_score"] < metadata.get("sufficiency_threshold", 0.72)
    ):
        return abstain_node(state, "evidence_below_threshold")
    if generator_client is None:
        return abstain_node(state, "generator_unavailable")
    if metadata.get("generation_attempts", 0) >= 2:
        return abstain_node(state, "invalid_citations")
    if direct:
        messages = build_direct_answer_prompt(state["original_query"])
    else:
        packed = pack_evidence_context(
            records,
            max_chunks=metadata.get("top_k_context", 6),
            max_characters=state["max_context_chars"],
        )
        if not packed.selected_evidence:
            return abstain_node(state, "context_budget_exceeded")
        state["evidence"] = [e.model_dump() for e in packed.selected_evidence]
        metadata["packed_context"] = packed.formatted_context
        metadata["context_characters"] = packed.total_characters
        if metadata.get("citation_validation_failed"):
            messages = build_citation_correction_prompt(
                state["original_query"],
                packed.formatted_context,
                state["answer"] or "",
                metadata.get("citation_errors", []),
            )
        else:
            messages = build_grounded_prompt(state["original_query"], packed.formatted_context)
    metadata["generation_attempts"] = metadata.get("generation_attempts", 0) + 1
    try:
        response = generator_client.generate(messages, temperature=metadata.get("temperature", 0.0))
        if not response.content.strip():
            raise ValueError("empty answer")
        state["answer"] = response.content
        state["estimated_input_tokens"] += response.prompt_tokens
        state["estimated_output_tokens"] += response.completion_tokens
    except Exception as exc:
        from evidenceops.domain.errors import OllamaTimeoutError

        reason = (
            "generator_timeout" if isinstance(exc, OllamaTimeoutError) else "generator_unavailable"
        )
        metadata.setdefault("failures", []).append({"stage": "generation", "code": reason})
        return abstain_node(state, reason)
    return state


@validated_node
def validate_citations_node(state: dict[str, Any]) -> dict[str, Any]:
    if state["abstention_reason"]:
        return state
    metadata = state["metadata"]
    direct = (
        state["route"] == QueryRoute.DIRECT
        and not metadata.get("require_citations", True)
        and RegexFeatureExtractor()
        .extract(state["original_query"])
        .predicted_external_knowledge_probability
        < 0.20
    )
    allowed = {e["citation_id"] for e in state["evidence"]}
    validation = validate_answer_citations(
        state["answer"] or "", allowed, require_citations=not direct
    )
    state["citations"] = validation.cited_ids
    metadata["citation_validation_failed"] = not validation.is_valid
    metadata["citation_errors"] = validation.errors
    if not validation.is_valid and metadata.get("generation_attempts", 0) >= 2:
        return abstain_node(state, "invalid_citations")
    return state


@validated_node
def abstain_node(
    state: dict[str, Any],
    reason: str | AbstentionReason = AbstentionReason.EVIDENCE_BELOW_THRESHOLD,
) -> dict[str, Any]:
    state["status"] = RunStatus.ABSTAINED
    state["next_action"] = None
    state["abstention_reason"] = state["abstention_reason"] or str(reason)
    state["answer"] = f"Unable to provide a grounded answer: {state['abstention_reason']}."
    state["citations"] = []
    return state


@validated_node
def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    state["next_action"] = None
    if state["status"] not in {RunStatus.ABSTAINED, RunStatus.FAILED}:
        state["status"] = RunStatus.COMPLETED
    return state

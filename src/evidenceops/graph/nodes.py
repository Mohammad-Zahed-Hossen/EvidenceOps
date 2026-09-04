"""Individual orchestration node functions for LangGraph workflow."""

from __future__ import annotations

from typing import Any

from evidenceops.controller.contracts import FeatureExtractor, RetrievalController
from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.controller.heuristic import HeuristicRetrievalController
from evidenceops.domain.enums import AbstentionReason, Action, EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.evidence.adapter import adapt_retrieval_results
from evidenceops.evidence.citations import assign_citations, validate_answer_citations
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


def initialize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Initialize workflow state with running status."""
    updated = dict(state)
    updated["status"] = RunStatus.RUNNING
    return updated


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


def controller_decide_node(
    state: dict[str, Any],
    controller: RetrievalController | None = None,
) -> dict[str, Any]:
    """Apply deterministic heuristic controller rules to select the next action."""
    updated = dict(state)
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


def retrieve_node(
    state: dict[str, Any],
    sparse_retriever: Any = None,
    dense_retriever: Any = None,
    hybrid_retriever: Any = None,
) -> dict[str, Any]:
    """Execute local retrieval call and adapt raw results into evidence records."""
    updated = dict(state)
    updated["retrieval_calls"] = updated.get("retrieval_calls", 0) + 1
    query = str(updated.get("active_query", updated.get("original_query", "")))
    route = updated.get("route")

    retriever = None
    method = "sparse"
    if route in (QueryRoute.DENSE, "dense") and dense_retriever is not None:
        retriever = dense_retriever
        method = "dense"
    elif route in (QueryRoute.HYBRID, "hybrid") and hybrid_retriever is not None:
        retriever = hybrid_retriever
        method = "hybrid"
    elif sparse_retriever is not None:
        retriever = sparse_retriever
        method = "sparse"
    elif hybrid_retriever is not None:
        retriever = hybrid_retriever
        method = "hybrid"
    elif dense_retriever is not None:
        retriever = dense_retriever
        method = "dense"

    if retriever is not None:
        raw_results = retriever.search(query, limit=10)
    else:
        raw_results = ()

    new_evidence = adapt_retrieval_results(raw_results)

    existing_evidence_data = updated.get("evidence", [])
    if existing_evidence_data:
        existing_records = [
            EvidenceRecord.model_validate(e) if isinstance(e, dict) else e
            for e in existing_evidence_data
        ]
        merged: dict[str, EvidenceRecord] = {e.chunk_id: e for e in existing_records}
        for item in new_evidence:
            if (
                item.chunk_id not in merged
                or item.retrieval_rank < merged[item.chunk_id].retrieval_rank
            ):
                merged[item.chunk_id] = item
        all_records = list(merged.values())
    else:
        all_records = list(new_evidence)

    assigned = assign_citations(all_records)
    updated["evidence"] = [e.model_dump(mode="python") for e in assigned]

    action_enum = {
        "dense": Action.RETRIEVE_DENSE,
        "hybrid": Action.RETRIEVE_HYBRID,
    }.get(method, Action.RETRIEVE_SPARSE)
    route_enum = None
    if route:
        route_enum = route if isinstance(route, QueryRoute) else QueryRoute(route)

    attempt_record = {
        "action": action_enum.value,
        "query": query,
        "route": route_enum.value if route_enum else None,
        "candidates_returned": len(raw_results),
        "accepted_evidence": len(new_evidence),
        "latency_ms": 0.0,
        "cache_hit": False,
        "error": None,
    }
    attempts = list(updated.get("attempts", []))
    attempts.append(attempt_record)
    updated["attempts"] = attempts
    return updated


def rerank_node(state: dict[str, Any], reranker: Any = None) -> dict[str, Any]:
    """Optionally rerank retrieved evidence candidates using local cross-encoder."""
    updated = dict(state)
    if reranker is None or not updated.get("evidence"):
        return updated

    return updated


def evaluate_evidence_node(state: dict[str, Any]) -> dict[str, Any]:
    """Evaluate sufficiency score and contradiction conflicts across accumulated evidence."""
    updated = dict(state)
    evidence_data = updated.get("evidence", [])
    evidence_records = [
        EvidenceRecord.model_validate(e) if isinstance(e, dict) else e for e in evidence_data
    ]
    query = str(updated.get("active_query", updated.get("original_query", "")))

    result = evaluate_sufficiency(query=query, evidence=evidence_records)
    conflict_res = detect_evidence_conflicts(evidence_records)
    conflict = conflict_res.conflict_score

    updated["sufficiency_score"] = round(result.composite_score, 4)
    updated["conflict_score"] = round(conflict, 4)

    if conflict >= 0.50:
        updated["evidence_status"] = EvidenceStatus.CONFLICTING
    else:
        updated["evidence_status"] = result.status

    return updated


def reformulate_node(
    state: dict[str, Any],
    reformulator: QueryReformulator | None = None,
) -> dict[str, Any]:
    """Increment iteration and produce a deterministic alternative query."""
    updated = dict(state)
    updated["iteration_count"] = updated.get("iteration_count", 0) + 1
    active_reformulator = reformulator or LocalQueryReformulator()
    query = str(updated.get("active_query", updated.get("original_query", "")))
    attempts = updated.get("attempts", [])
    prev_queries = [str(a.get("query")) for a in attempts if isinstance(a, dict) and a.get("query")]
    new_query = active_reformulator.reformulate(query, previous_queries=prev_queries)
    updated["active_query"] = new_query
    return updated


def generate_node(
    state: dict[str, Any],
    generator_client: GeneratorClient | None = None,
) -> dict[str, Any]:
    """Generate grounded answer using packed evidence and local generator."""
    updated = dict(state)
    metadata = updated.setdefault("metadata", {})
    metadata["generation_attempts"] = metadata.get("generation_attempts", 0) + 1

    next_action = updated.get("next_action")
    evidence_data = updated.get("evidence", [])
    evidence_records = [
        EvidenceRecord.model_validate(e) if isinstance(e, dict) else e for e in evidence_data
    ]

    if next_action in (Action.DIRECT_ANSWER, "direct_answer") or not evidence_records:
        messages = build_direct_answer_prompt(str(updated.get("active_query", "")))
    else:
        packed = pack_evidence_context(
            evidence_records,
            max_chunks=6,
            max_characters=updated.get("max_context_chars", 24000),
        )
        if metadata.get("citation_validation_failed") and metadata.get("citation_errors"):
            messages = build_citation_correction_prompt(
                query=str(updated.get("active_query", "")),
                evidence_text=packed.formatted_context,
                previous_answer=str(updated.get("answer", "")),
                validation_errors=metadata.get("citation_errors", []),
            )
        else:
            messages = build_grounded_prompt(
                str(updated.get("active_query", "")),
                packed.formatted_context,
            )

    if generator_client is not None:
        try:
            resp = generator_client.generate(messages)
            updated["answer"] = resp.content
            updated["estimated_input_tokens"] = (
                updated.get("estimated_input_tokens", 0) + resp.prompt_tokens
            )
            updated["estimated_output_tokens"] = (
                updated.get("estimated_output_tokens", 0) + resp.completion_tokens
            )
        except Exception as exc:
            from evidenceops.domain.errors import (
                OllamaTimeoutError,
                OllamaUnavailableError,
            )

            if isinstance(exc, OllamaTimeoutError):
                reason = AbstentionReason.GENERATOR_TIMEOUT
            elif isinstance(exc, OllamaUnavailableError):
                reason = AbstentionReason.GENERATOR_UNAVAILABLE
            else:
                reason = AbstentionReason.GENERATOR_UNAVAILABLE

            updated["status"] = RunStatus.ABSTAINED
            updated["abstention_reason"] = reason.value
            updated["answer"] = f"Local generation unavailable: {exc}"
            metadata["error"] = str(exc)
    else:
        updated["answer"] = "No generator configured."

    return updated


def validate_citations_node(state: dict[str, Any]) -> dict[str, Any]:
    """Verify that all inline citations reference real retrieved evidence."""
    updated = dict(state)
    if updated.get("status") in (RunStatus.ABSTAINED, "abstained"):
        return updated
    answer = str(updated.get("answer") or "")
    evidence_data = updated.get("evidence", [])
    evidence_records = [
        EvidenceRecord.model_validate(e) if isinstance(e, dict) else e for e in evidence_data
    ]

    allowed_ids = {e.citation_id for e in evidence_records if e.citation_id}
    validation = validate_answer_citations(answer, allowed_ids)
    metadata = updated.setdefault("metadata", {})
    updated["citations"] = validation.cited_ids

    if validation.is_valid:
        metadata["citation_validation_failed"] = False
        metadata.pop("citation_errors", None)
    else:
        metadata["citation_validation_failed"] = True
        metadata["citation_errors"] = validation.errors

    return updated


def abstain_node(
    state: dict[str, Any],
    reason: str | AbstentionReason = AbstentionReason.EVIDENCE_BELOW_THRESHOLD,
) -> dict[str, Any]:
    """Transition state to ABSTAINED with transparent reason."""
    updated = dict(state)
    updated["status"] = RunStatus.ABSTAINED
    if not updated.get("abstention_reason"):
        reason_str = reason.value if hasattr(reason, "value") else str(reason)
        updated["abstention_reason"] = reason_str
    else:
        reason_str = str(updated["abstention_reason"])

    if not updated.get("answer") or not str(updated.get("answer", "")).strip():
        updated["answer"] = f"Unable to provide a grounded answer: {reason_str}."
    return updated


def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Mark successful execution as COMPLETED."""
    updated = dict(state)
    if updated.get("status") not in (RunStatus.ABSTAINED, "abstained"):
        updated["status"] = RunStatus.COMPLETED
    return updated

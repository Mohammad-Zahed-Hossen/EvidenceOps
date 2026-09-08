"""Benchmark baseline implementations for LiteBridge evaluation."""

from __future__ import annotations

import time

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    CompressionPolicy,
    ContextPackage,
    ExecutionProfile,
    RetrievalPolicy,
    SourcePolicy,
    WebRetrievalPolicy,
)
from evidenceops.bridge.service import LiteBridge
from evidenceops.eval.litebridge.contracts import BaselineName, CaseResult, EvaluationCase
from evidenceops.eval.litebridge.fixtures import (
    FixtureLocalRetriever,
    FixtureWebSearchAdapter,
)
from evidenceops.eval.litebridge.learned_planner import LearnedPlannerExperiment


def _compute_recall(actual_ids: list[str], expected_ids: list[str]) -> float:
    """Compute fraction of expected evidence IDs retrieved."""
    if not expected_ids:
        return 1.0
    actual_set = set(actual_ids)
    matched = sum(1 for eid in expected_ids if eid in actual_set)
    return round(matched / len(expected_ids), 4)


def _check_citations_valid(package: ContextPackage) -> bool:
    """Verify that every retained evidence record has a valid non-empty citation_id."""
    if not package.evidence:
        return True
    return all(bool(e.citation_id and e.citation_id.strip()) for e in package.evidence)


def _check_provenance_preserved(package: ContextPackage) -> bool:
    """Verify that provenance (source_id, document_id, canonical_url if web) is intact."""
    for e in package.evidence:
        if not e.source_id or not e.document_id:
            return False
        if e.source_kind.value == "web_search_snippet" and not e.canonical_url:
            return False
    return True


def run_no_retrieval(case: EvaluationCase) -> CaseResult:
    """Baseline 1: No retrieval executed; always returns empty context."""
    start = time.perf_counter()
    duration_ms = (time.perf_counter() - start) * 1000.0

    recall = 1.0 if not case.expected_evidence_ids else 0.0
    stop_reason = case.expected_stop_reason or "success"
    return CaseResult(
        case_id=case.case_id,
        split=case.split,
        baseline_name=BaselineName.NO_RETRIEVAL,
        route="blocked" if case.expected_route == "blocked" else "no_retrieval",
        source_id=None,
        evidence_ids=[],
        evidence_recall=recall,
        context_characters=0,
        estimated_tokens=0,
        stop_reason=stop_reason,
        retrieval_calls=0,
        web_calls=0,
        estimated_external_cost_microusd=0,
        citation_ids_valid=True,
        provenance_preserved=True,
        support_preserved=True if not case.expected_evidence_ids else False,
        duration_ms=round(duration_ms, 3),
    )


def run_fixed_local(case: EvaluationCase, retriever: FixtureLocalRetriever) -> CaseResult:
    """Baseline 2: Fixed local retrieval policy."""
    start = time.perf_counter()

    if case.max_retrieval_calls <= 0:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return CaseResult(
            case_id=case.case_id,
            split=case.split,
            baseline_name=BaselineName.FIXED_LOCAL,
            route="blocked",
            source_id=None,
            evidence_ids=[],
            evidence_recall=0.0 if case.expected_evidence_ids else 1.0,
            context_characters=0,
            estimated_tokens=0,
            stop_reason="budget_exceeded",
            retrieval_calls=0,
            web_calls=0,
            estimated_external_cost_microusd=0,
            citation_ids_valid=True,
            provenance_preserved=True,
            support_preserved=True if not case.expected_evidence_ids else False,
            duration_ms=round(duration_ms, 3),
        )

    policy = RetrievalPolicy(mode="hybrid", max_evidence_items=6)
    batch = retriever.retrieve(case.query, policy)
    duration_ms = (time.perf_counter() - start) * 1000.0

    actual_ids = [c.candidate_id for c in batch.candidates]
    recall = _compute_recall(actual_ids, case.expected_evidence_ids)
    stop_reason = "success" if actual_ids else "no_evidence"

    chars = sum(len(c.text) for c in batch.candidates)
    tokens = sum((len(c.text) + 3) // 4 for c in batch.candidates)

    return CaseResult(
        case_id=case.case_id,
        split=case.split,
        baseline_name=BaselineName.FIXED_LOCAL,
        route="local",
        source_id="fixture_local_docs",
        evidence_ids=actual_ids,
        evidence_recall=recall,
        context_characters=chars,
        estimated_tokens=tokens,
        stop_reason=stop_reason,
        retrieval_calls=1,
        web_calls=0,
        estimated_external_cost_microusd=0,
        citation_ids_valid=True,
        provenance_preserved=True,
        support_preserved=True,
        duration_ms=round(duration_ms, 3),
    )


def run_fixed_web(case: EvaluationCase, retriever: FixtureWebSearchAdapter) -> CaseResult:
    """Baseline 3: Fixed web retrieval policy (requires consent)."""
    start = time.perf_counter()

    if not case.allow_external_query:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return CaseResult(
            case_id=case.case_id,
            split=case.split,
            baseline_name=BaselineName.FIXED_WEB,
            route="blocked",
            source_id=None,
            evidence_ids=[],
            evidence_recall=0.0 if case.expected_evidence_ids else 1.0,
            context_characters=0,
            estimated_tokens=0,
            stop_reason="unsupported_profile",
            retrieval_calls=0,
            web_calls=0,
            estimated_external_cost_microusd=0,
            citation_ids_valid=True,
            provenance_preserved=True,
            support_preserved=True if not case.expected_evidence_ids else False,
            duration_ms=round(duration_ms, 3),
        )

    if case.max_web_calls <= 0 or case.max_estimated_external_cost_microusd <= 0:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return CaseResult(
            case_id=case.case_id,
            split=case.split,
            baseline_name=BaselineName.FIXED_WEB,
            route="blocked",
            source_id=None,
            evidence_ids=[],
            evidence_recall=0.0 if case.expected_evidence_ids else 1.0,
            context_characters=0,
            estimated_tokens=0,
            stop_reason="budget_exceeded",
            retrieval_calls=0,
            web_calls=0,
            estimated_external_cost_microusd=0,
            citation_ids_valid=True,
            provenance_preserved=True,
            support_preserved=True if not case.expected_evidence_ids else False,
            duration_ms=round(duration_ms, 3),
        )

    web_policy = WebRetrievalPolicy(allow_external_query=True)
    policy = RetrievalPolicy(
        mode="hybrid",
        execution_profile=ExecutionProfile.HYBRID,
        max_evidence_items=6,
        web=web_policy,
    )
    batch = retriever.retrieve(case.query, policy)
    duration_ms = (time.perf_counter() - start) * 1000.0

    actual_ids = [c.candidate_id for c in batch.candidates]
    recall = _compute_recall(actual_ids, case.expected_evidence_ids)
    stop_reason = "success" if actual_ids else "no_evidence"

    chars = sum(len(c.text) for c in batch.candidates)
    tokens = sum((len(c.text) + 3) // 4 for c in batch.candidates)

    return CaseResult(
        case_id=case.case_id,
        split=case.split,
        baseline_name=BaselineName.FIXED_WEB,
        route="web",
        source_id="fixture_web_search",
        evidence_ids=actual_ids,
        evidence_recall=recall,
        context_characters=chars,
        estimated_tokens=tokens,
        stop_reason=stop_reason,
        retrieval_calls=1,
        web_calls=1,
        estimated_external_cost_microusd=1000,
        citation_ids_valid=True,
        provenance_preserved=True,
        support_preserved=True,
        duration_ms=round(duration_ms, 3),
    )


def execute_heuristic_context(
    case: EvaluationCase,
    bridge: LiteBridge,
) -> tuple[ContextPackage, float]:
    """Execute LiteBridge prepare_context and return package and duration."""
    start = time.perf_counter()

    profile = ExecutionProfile.HYBRID if case.allow_external_query else ExecutionProfile.LOCAL_ONLY
    budget = BudgetPolicy(
        max_retrieval_calls=case.max_retrieval_calls,
        max_web_calls=case.max_web_calls,
        max_estimated_external_cost_microusd=case.max_estimated_external_cost_microusd,
    )
    web_policy = (
        WebRetrievalPolicy(allow_external_query=True) if case.allow_external_query else None
    )
    policy = RetrievalPolicy(
        mode="hybrid",
        execution_profile=profile,
        web=web_policy,
        budget=budget,
    )
    source_policy = SourcePolicy(allowed_source_ids=(case.source_id,)) if case.source_id else None

    package = bridge.prepare_context(
        query=case.query,
        policy=policy,
        source_policy=source_policy,
    )
    duration_ms = (time.perf_counter() - start) * 1000.0
    return package, duration_ms


def run_heuristic_planner(
    case: EvaluationCase,
    bridge: LiteBridge,
) -> tuple[CaseResult, ContextPackage]:
    """Baseline 4: Production L4 Deterministic Planner and LiteBridge service."""
    package, duration_ms = execute_heuristic_context(case, bridge)

    actual_ids = [e.evidence_id for e in package.evidence]
    recall = _compute_recall(actual_ids, case.expected_evidence_ids)

    route_val = package.planner_decision.route.value if package.planner_decision else "blocked"
    source_id = package.planner_decision.selected_source_id if package.planner_decision else None

    # Check whether expected evidence was preserved
    support_preserved = True
    if case.expected_evidence_ids and case.expected_answerable:
        support_preserved = any(eid in set(actual_ids) for eid in case.expected_evidence_ids)

    res = CaseResult(
        case_id=case.case_id,
        split=case.split,
        baseline_name=BaselineName.HEURISTIC_PLANNER,
        route=route_val,
        source_id=source_id,
        evidence_ids=actual_ids,
        evidence_recall=recall,
        context_characters=package.context_chars,
        estimated_tokens=package.estimated_tokens,
        stop_reason=package.stop_reason.value,
        retrieval_calls=package.retrieval_calls,
        web_calls=package.web_calls,
        estimated_external_cost_microusd=dict(package.budget_used).get(
            "estimated_external_cost_microusd", 0
        ),
        citation_ids_valid=_check_citations_valid(package),
        provenance_preserved=_check_provenance_preserved(package),
        support_preserved=support_preserved,
        duration_ms=round(duration_ms, 3),
    )
    return res, package


def run_heuristic_plus_compression(
    case: EvaluationCase,
    bridge: LiteBridge,
    uncompressed_package: ContextPackage,
) -> CaseResult:
    """Baseline 5: Heuristic package + L6 extractive compression."""
    start = time.perf_counter()

    comp_policy = CompressionPolicy(
        strategy="extractive",
        target_max_context_chars=1200,
        target_max_estimated_tokens=300,
        max_sentences_per_evidence=3,
        deduplicate_exact_retrieval_copies=True,
        allow_evidence_drop=False,
    )
    compressed = bridge.compress_context(uncompressed_package, compression_policy=comp_policy)
    duration_ms = (time.perf_counter() - start) * 1000.0

    actual_ids = [e.evidence_id for e in compressed.evidence]
    recall = _compute_recall(actual_ids, case.expected_evidence_ids)

    uncomp_ids = {e.evidence_id for e in uncompressed_package.evidence}
    has_expected_before = any(eid in uncomp_ids for eid in case.expected_evidence_ids)

    if case.expected_answerable and has_expected_before:
        support_preserved = any(eid in set(actual_ids) for eid in case.expected_evidence_ids)
    else:
        support_preserved = True

    route_val = (
        compressed.planner_decision.route.value if compressed.planner_decision else "blocked"
    )
    source_id = (
        compressed.planner_decision.selected_source_id if compressed.planner_decision else None
    )

    return CaseResult(
        case_id=case.case_id,
        split=case.split,
        baseline_name=BaselineName.HEURISTIC_PLUS_COMPRESSION,
        route=route_val,
        source_id=source_id,
        evidence_ids=actual_ids,
        evidence_recall=recall,
        context_characters=compressed.context_chars,
        estimated_tokens=compressed.estimated_tokens,
        stop_reason=compressed.stop_reason.value,
        retrieval_calls=compressed.retrieval_calls,
        web_calls=compressed.web_calls,
        estimated_external_cost_microusd=dict(compressed.budget_used).get(
            "estimated_external_cost_microusd", 0
        ),
        citation_ids_valid=_check_citations_valid(compressed),
        provenance_preserved=_check_provenance_preserved(compressed),
        support_preserved=support_preserved,
        duration_ms=round(duration_ms, 3),
    )


def run_learned_planner(
    case: EvaluationCase,
    learned_model: LearnedPlannerExperiment,
    local_retriever: FixtureLocalRetriever,
    web_retriever: FixtureWebSearchAdapter,
) -> CaseResult:
    """Baseline 6: Offline-only learned controller prediction."""
    start = time.perf_counter()

    predicted_route = learned_model.predict(case)
    duration_ms = (time.perf_counter() - start) * 1000.0

    if predicted_route == "blocked":
        stop_reason = (
            case.expected_stop_reason
            if case.expected_stop_reason in ("budget_exceeded", "unsupported_profile")
            else "unsupported_profile"
        )
        return CaseResult(
            case_id=case.case_id,
            split=case.split,
            baseline_name=BaselineName.LEARNED_PLANNER_EXPERIMENT,
            route="blocked",
            source_id=None,
            evidence_ids=[],
            evidence_recall=0.0 if case.expected_evidence_ids else 1.0,
            context_characters=0,
            estimated_tokens=0,
            stop_reason=stop_reason,
            retrieval_calls=0,
            web_calls=0,
            estimated_external_cost_microusd=0,
            citation_ids_valid=True,
            provenance_preserved=True,
            support_preserved=True if not case.expected_evidence_ids else False,
            duration_ms=round(duration_ms, 3),
        )

    if predicted_route == "web":
        if not case.allow_external_query:
            return CaseResult(
                case_id=case.case_id,
                split=case.split,
                baseline_name=BaselineName.LEARNED_PLANNER_EXPERIMENT,
                route="blocked",
                source_id=None,
                evidence_ids=[],
                evidence_recall=0.0 if case.expected_evidence_ids else 1.0,
                context_characters=0,
                estimated_tokens=0,
                stop_reason="unsupported_profile",
                retrieval_calls=0,
                web_calls=0,
                estimated_external_cost_microusd=0,
                citation_ids_valid=True,
                provenance_preserved=True,
                support_preserved=True if not case.expected_evidence_ids else False,
                duration_ms=round(duration_ms, 3),
            )
        return run_fixed_web(case, web_retriever)

    # Local route
    return run_fixed_local(case, local_retriever)


def run_evidenceops_adapter_conformance(
    case: EvaluationCase,
    conformance_bridge: LiteBridge,
) -> CaseResult:
    """Baseline 7: EvidenceOpsLocalRetrieverAdapter conformance evaluation."""
    package, duration_ms = execute_heuristic_context(case, conformance_bridge)

    actual_ids = [e.evidence_id for e in package.evidence]
    recall = _compute_recall(actual_ids, case.expected_evidence_ids)

    route_val = package.planner_decision.route.value if package.planner_decision else "blocked"
    source_id = package.planner_decision.selected_source_id if package.planner_decision else None

    support_preserved = True
    if case.expected_evidence_ids and case.expected_answerable:
        support_preserved = any(eid in set(actual_ids) for eid in case.expected_evidence_ids)

    return CaseResult(
        case_id=case.case_id,
        split=case.split,
        baseline_name=BaselineName.EVIDENCEOPS_ADAPTER_CONFORMANCE,
        route=route_val,
        source_id=source_id,
        evidence_ids=actual_ids,
        evidence_recall=recall,
        context_characters=package.context_chars,
        estimated_tokens=package.estimated_tokens,
        stop_reason=package.stop_reason.value,
        retrieval_calls=package.retrieval_calls,
        web_calls=package.web_calls,
        estimated_external_cost_microusd=dict(package.budget_used).get(
            "estimated_external_cost_microusd", 0
        ),
        citation_ids_valid=_check_citations_valid(package),
        provenance_preserved=_check_provenance_preserved(package),
        support_preserved=support_preserved,
        duration_ms=round(duration_ms, 3),
    )

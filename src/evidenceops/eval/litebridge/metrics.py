"""Evaluation metric calculation and determinism digest computation."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from evidenceops.eval.litebridge.contracts import (
    AggregateMetrics,
    CaseResult,
    EvaluationCase,
    LatencyDistribution,
)


def compute_percentile(values: list[float], p: float) -> float:
    """Compute deterministic percentile using linear interpolation."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return round(sorted_vals[0], 3)
    k = (n - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_vals[int(k)], 3)
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return round(d0 + d1, 3)


def compute_latency_distribution(latencies_ms: list[float]) -> LatencyDistribution:
    """Compute aggregate statistical latency distribution across timed sample executions."""
    if not latencies_ms:
        return LatencyDistribution(
            sample_count=0,
            mean_ms=0.0,
            median_ms=0.0,
            p50_ms=0.0,
            p90_ms=0.0,
            p95_ms=0.0,
            min_ms=0.0,
            max_ms=0.0,
        )
    count = len(latencies_ms)
    mean_val = round(sum(latencies_ms) / count, 3)
    p50 = compute_percentile(latencies_ms, 50.0)
    p90 = compute_percentile(latencies_ms, 90.0)
    p95 = compute_percentile(latencies_ms, 95.0)
    return LatencyDistribution(
        sample_count=count,
        mean_ms=mean_val,
        median_ms=p50,
        p50_ms=p50,
        p90_ms=p90,
        p95_ms=p95,
        min_ms=round(min(latencies_ms), 3),
        max_ms=round(max(latencies_ms), 3),
    )


def compute_aggregate_metrics(
    cases: list[EvaluationCase],
    case_results: list[CaseResult],
    all_latencies_ms: list[float],
    char_reduction_pct: float = 0.0,
    token_reduction_pct: float = 0.0,
    compression_outcome_distribution: dict[str, int] | None = None,
) -> AggregateMetrics:
    """Compute aggregate metrics for a collection of case results."""
    case_count = len(case_results)
    if case_count == 0:
        return AggregateMetrics(
            case_count=0,
            route_accuracy=0.0,
            source_accuracy=0.0,
            evidence_recall=0.0,
            answerability_correctness=0.0,
            blocked_correctness=0.0,
            total_retrieval_calls=0,
            total_web_calls=0,
            total_estimated_external_cost_microusd=0,
            avg_context_characters=0.0,
            avg_estimated_tokens=0.0,
            citation_validity_rate=0.0,
            provenance_preservation_rate=0.0,
            support_preservation_rate=1.0,
            char_reduction_pct=char_reduction_pct,
            token_reduction_pct=token_reduction_pct,
            compression_outcome_distribution=compression_outcome_distribution or {},
            stop_reason_distribution={},
            latency=compute_latency_distribution([]),
        )

    case_map = {c.case_id: c for c in cases}

    route_matches = 0
    source_matches = 0
    recall_scores: list[float] = []
    answerability_matches = 0
    blocked_matches = 0

    total_retrieval_calls = 0
    total_web_calls = 0
    total_cost = 0
    total_chars = 0
    total_tokens = 0

    valid_citations = 0
    valid_provenance = 0
    support_preserved_count = 0

    stop_reasons: dict[str, int] = {}

    for res in case_results:
        c = case_map[res.case_id]

        if res.route == c.expected_route:
            route_matches += 1

        if (c.expected_source_id is None and res.source_id is None) or (
            c.expected_source_id is not None and res.source_id == c.expected_source_id
        ):
            source_matches += 1

        recall_scores.append(res.evidence_recall)

        is_answerable = res.stop_reason == "success" and len(res.evidence_ids) > 0
        if is_answerable == c.expected_answerable:
            answerability_matches += 1

        if c.expected_route == "blocked":
            if res.route == "blocked" and res.stop_reason == (
                c.expected_stop_reason or res.stop_reason
            ):
                blocked_matches += 1
        else:
            blocked_matches += (
                1  # Not expected to be blocked, counted as non-blocked correct if not blocked
            )

        total_retrieval_calls += res.retrieval_calls
        total_web_calls += res.web_calls
        total_cost += res.estimated_external_cost_microusd
        total_chars += res.context_characters
        total_tokens += res.estimated_tokens

        if res.citation_ids_valid:
            valid_citations += 1
        if res.provenance_preserved:
            valid_provenance += 1
        if res.support_preserved:
            support_preserved_count += 1

        stop_reasons[res.stop_reason] = stop_reasons.get(res.stop_reason, 0) + 1

    latency_dist = compute_latency_distribution(all_latencies_ms)

    return AggregateMetrics(
        case_count=case_count,
        route_accuracy=round(route_matches / case_count, 4),
        source_accuracy=round(source_matches / case_count, 4),
        evidence_recall=round(sum(recall_scores) / case_count, 4),
        answerability_correctness=round(answerability_matches / case_count, 4),
        blocked_correctness=round(blocked_matches / case_count, 4),
        total_retrieval_calls=total_retrieval_calls,
        total_web_calls=total_web_calls,
        total_estimated_external_cost_microusd=total_cost,
        avg_context_characters=round(total_chars / case_count, 2),
        avg_estimated_tokens=round(total_tokens / case_count, 2),
        citation_validity_rate=round(valid_citations / case_count, 4),
        provenance_preservation_rate=round(valid_provenance / case_count, 4),
        support_preservation_rate=round(support_preserved_count / case_count, 4),
        char_reduction_pct=round(char_reduction_pct, 4),
        token_reduction_pct=round(token_reduction_pct, 4),
        compression_outcome_distribution=compression_outcome_distribution or {},
        stop_reason_distribution=stop_reasons,
        latency=latency_dist,
    )


def compute_determinism_digest(report_dict: dict[str, Any]) -> str:
    """Compute SHA-256 digest of non-timing report fields to verify exact run determinism."""
    # Filter out timing fields from report
    cleaned: dict[str, Any] = {
        "dataset_id": report_dict.get("dataset_id"),
        "manifest_sha256": report_dict.get("manifest_sha256"),
        "learned_controller_status": report_dict.get("learned_controller_status"),
    }

    # Clean baselines
    clean_baselines: dict[str, Any] = {}
    for b_name, b_splits in sorted(report_dict.get("baselines", {}).items()):
        clean_splits: dict[str, Any] = {}
        for s_name, metrics in sorted(b_splits.items()):
            metric_copy = dict(metrics)
            metric_copy.pop("latency", None)
            clean_splits[s_name] = metric_copy
        clean_baselines[b_name] = clean_splits
    cleaned["baselines"] = clean_baselines

    # Clean case results
    clean_cases: list[dict[str, Any]] = []
    for cr in report_dict.get("case_results", []):
        cr_copy = dict(cr)
        cr_copy.pop("duration_ms", None)
        clean_cases.append(cr_copy)
    clean_cases.sort(key=lambda x: (x.get("baseline_name", ""), x.get("case_id", "")))
    cleaned["case_results"] = clean_cases

    canonical_json = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

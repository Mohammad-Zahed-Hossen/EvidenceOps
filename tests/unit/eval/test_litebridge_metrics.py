"""Tests for LiteBridge evaluation metric calculations and determinism digest."""

from evidenceops.eval.litebridge.contracts import (
    BaselineName,
    CaseResult,
    EvaluationCase,
    EvaluationSplit,
)
from evidenceops.eval.litebridge.metrics import (
    compute_aggregate_metrics,
    compute_determinism_digest,
    compute_latency_distribution,
    compute_percentile,
)


def test_percentile_and_latency_distribution():
    """Verify deterministic percentile and latency distribution calculation."""
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert compute_percentile(vals, 50.0) == 30.0
    assert compute_percentile(vals, 0.0) == 10.0
    assert compute_percentile(vals, 100.0) == 50.0

    dist = compute_latency_distribution([5.0, 10.0, 15.0, 20.0])
    assert dist.sample_count == 4
    assert dist.mean_ms == 12.5
    assert dist.min_ms == 5.0
    assert dist.max_ms == 20.0


def test_aggregate_metrics_hand_calculation():
    """Verify exact hand-calculated accuracy and recall metrics."""
    cases = [
        EvaluationCase(
            case_id="c1",
            split=EvaluationSplit.TRAIN,
            query="q1",
            expected_route="local",
            expected_source_id="src_loc",
            expected_evidence_ids=["e1"],
            expected_answerable=True,
            expected_stop_reason="success",
        ),
        EvaluationCase(
            case_id="c2",
            split=EvaluationSplit.TRAIN,
            query="q2",
            expected_route="blocked",
            expected_source_id=None,
            expected_evidence_ids=[],
            expected_answerable=False,
            expected_stop_reason="budget_exceeded",
        ),
    ]

    results = [
        CaseResult(
            case_id="c1",
            split=EvaluationSplit.TRAIN,
            baseline_name=BaselineName.HEURISTIC_PLANNER,
            route="local",
            source_id="src_loc",
            evidence_ids=["e1"],
            evidence_recall=1.0,
            context_characters=100,
            estimated_tokens=25,
            stop_reason="success",
            retrieval_calls=1,
            web_calls=0,
            estimated_external_cost_microusd=0,
            citation_ids_valid=True,
            provenance_preserved=True,
            support_preserved=True,
            duration_ms=10.0,
        ),
        CaseResult(
            case_id="c2",
            split=EvaluationSplit.TRAIN,
            baseline_name=BaselineName.HEURISTIC_PLANNER,
            route="blocked",
            source_id=None,
            evidence_ids=[],
            evidence_recall=1.0,
            context_characters=0,
            estimated_tokens=0,
            stop_reason="budget_exceeded",
            retrieval_calls=0,
            web_calls=0,
            estimated_external_cost_microusd=0,
            citation_ids_valid=True,
            provenance_preserved=True,
            support_preserved=True,
            duration_ms=2.0,
        ),
    ]

    agg = compute_aggregate_metrics(
        cases=cases,
        case_results=results,
        all_latencies_ms=[10.0, 2.0],
    )

    assert agg.case_count == 2
    assert agg.route_accuracy == 1.0
    assert agg.source_accuracy == 1.0
    assert agg.evidence_recall == 1.0
    assert agg.answerability_correctness == 1.0
    assert agg.blocked_correctness == 1.0
    assert agg.total_retrieval_calls == 1
    assert agg.support_preservation_rate == 1.0


def test_determinism_digest_ignores_duration():
    """Verify that determinism digest is identical even when execution durations vary."""
    report_a = {
        "dataset_id": "test_ds",
        "manifest_sha256": "sha123",
        "learned_controller_status": "not_adopted",
        "baselines": {
            "no_retrieval": {
                "overall": {
                    "case_count": 1,
                    "route_accuracy": 1.0,
                    "latency": {
                        "sample_count": 1,
                        "mean_ms": 15.2,
                        "median_ms": 15.2,
                        "p50_ms": 15.2,
                        "p90_ms": 15.2,
                        "p95_ms": 15.2,
                        "min_ms": 15.2,
                        "max_ms": 15.2,
                    },
                }
            }
        },
        "case_results": [
            {
                "case_id": "c1",
                "baseline_name": "no_retrieval",
                "duration_ms": 15.2,
                "route": "local",
            }
        ],
    }

    report_b = {
        "dataset_id": "test_ds",
        "manifest_sha256": "sha123",
        "learned_controller_status": "not_adopted",
        "baselines": {
            "no_retrieval": {
                "overall": {
                    "case_count": 1,
                    "route_accuracy": 1.0,
                    "latency": {
                        "sample_count": 1,
                        "mean_ms": 99.9,
                        "median_ms": 99.9,
                        "p50_ms": 99.9,
                        "p90_ms": 99.9,
                        "p95_ms": 99.9,
                        "min_ms": 99.9,
                        "max_ms": 99.9,
                    },
                }
            }
        },
        "case_results": [
            {
                "case_id": "c1",
                "baseline_name": "no_retrieval",
                "duration_ms": 99.9,
                "route": "local",
            }
        ],
    }

    digest_a = compute_determinism_digest(report_a)
    digest_b = compute_determinism_digest(report_b)
    assert digest_a == digest_b

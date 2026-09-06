"""Unit tests for leaderboard and run manifest artifact generators."""

from __future__ import annotations

from evidenceops.evaluation.artifacts import (
    BenchmarkRunManifest,
    generate_leaderboard_markdown,
    generate_run_manifest,
)
from evidenceops.evaluation.scoring import AggregateEvaluationReport
from evidenceops.evaluation.statistics import BootstrapResult


def test_generate_leaderboard_markdown() -> None:
    rep_naive = AggregateEvaluationReport(
        system_name="NaiveDenseRAG",
        sample_count=20,
        mean_recall_at_1=0.45,
        mean_recall_at_3=0.60,
        mean_recall_at_5=0.70,
        mean_mrr=0.55,
        mean_ndcg_at_10=0.58,
        mean_atomic_fact_f1=0.50,
        mean_citation_validity_rate=0.75,
        mean_citation_precision=0.70,
        abstention_accuracy=0.65,
        mean_latency_ms=150.0,
        mean_retrieval_calls=1.0,
        mean_generation_calls=1.0,
        mean_peak_memory_mb=45.0,
    )
    rep_ops = AggregateEvaluationReport(
        system_name="HeuristicEvidenceOps",
        sample_count=20,
        mean_recall_at_1=0.80,
        mean_recall_at_3=0.90,
        mean_recall_at_5=0.95,
        mean_mrr=0.85,
        mean_ndcg_at_10=0.88,
        mean_atomic_fact_f1=0.82,
        mean_citation_validity_rate=0.98,
        mean_citation_precision=0.92,
        abstention_accuracy=0.95,
        mean_latency_ms=250.0,
        mean_retrieval_calls=1.5,
        mean_generation_calls=1.0,
        mean_peak_memory_mb=60.0,
    )

    bootstraps = {
        "HeuristicEvidenceOps_vs_NaiveDenseRAG": [
            BootstrapResult(
                metric_name="Recall@1",
                baseline_mean=0.45,
                system_mean=0.80,
                mean_difference=0.35,
                ci_lower=0.25,
                ci_upper=0.45,
                p_value=0.001,
                statistically_significant=True,
            )
        ]
    }

    md = generate_leaderboard_markdown(
        system_reports=[rep_naive, rep_ops],
        bootstrap_results=bootstraps,
        split_name="val",
    )

    assert "# EvidenceOps Benchmark Leaderboard" in md
    assert "NaiveDenseRAG" in md
    assert "HeuristicEvidenceOps" in md
    assert "| System | Recall@1 | MRR@10 | nDCG@10 | Fact F1 |" in md
    assert "Statistical Significance" in md


def test_generate_run_manifest() -> None:
    rep_naive = AggregateEvaluationReport(
        system_name="NaiveDenseRAG",
        sample_count=5,
        mean_recall_at_1=0.5,
        mean_recall_at_3=0.6,
        mean_recall_at_5=0.7,
        mean_mrr=0.55,
        mean_ndcg_at_10=0.58,
        mean_atomic_fact_f1=0.5,
        mean_citation_validity_rate=0.8,
        mean_citation_precision=0.7,
        abstention_accuracy=0.6,
        mean_latency_ms=100.0,
        mean_retrieval_calls=1.0,
        mean_generation_calls=1.0,
        mean_peak_memory_mb=40.0,
    )

    manifest = generate_run_manifest(
        run_id="bench_001",
        dataset_id="evidenceops-controlled-v1",
        split_name="val",
        system_reports=[rep_naive],
        sample_scores=[],
        environment_profile={"cpu": "Ryzen 5 5600G", "ram_gb": 8},
    )

    assert isinstance(manifest, BenchmarkRunManifest)
    assert manifest.run_id == "bench_001"
    assert manifest.dataset_id == "evidenceops-controlled-v1"
    assert len(manifest.system_reports) == 1
    assert manifest.environment_profile["cpu"] == "Ryzen 5 5600G"

"""Artifact generators for benchmark leaderboards and machine-readable run manifests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from evidenceops.evaluation.scoring import AggregateEvaluationReport, SampleEvaluationScore
from evidenceops.evaluation.statistics import BootstrapResult


class BenchmarkRunManifest(BaseModel):
    """Complete machine-readable record of an evaluation benchmark run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    dataset_id: str
    split_name: str
    timestamp: str
    system_reports: list[AggregateEvaluationReport]
    sample_scores: list[SampleEvaluationScore]
    environment_profile: dict[str, Any]


def generate_run_manifest(
    run_id: str,
    dataset_id: str,
    split_name: str,
    system_reports: list[AggregateEvaluationReport],
    sample_scores: list[SampleEvaluationScore],
    environment_profile: dict[str, Any],
    timestamp: str | None = None,
) -> BenchmarkRunManifest:
    """Construct an immutable benchmark run manifest."""
    ts = timestamp or datetime.now(UTC).isoformat()
    return BenchmarkRunManifest(
        run_id=run_id,
        dataset_id=dataset_id,
        split_name=split_name,
        timestamp=ts,
        system_reports=system_reports,
        sample_scores=sample_scores,
        environment_profile=environment_profile,
    )


def generate_leaderboard_markdown(
    system_reports: list[AggregateEvaluationReport],
    bootstrap_results: dict[str, list[BootstrapResult]],
    split_name: str,
) -> str:
    """Generate a clean GitHub-flavored Markdown leaderboard and significance report."""
    lines = [
        f"# EvidenceOps Benchmark Leaderboard ({split_name.upper()} split)",
        "",
        "## Aggregate Performance Overview",
        "",
        (
            "| System | Recall@1 | MRR@10 | nDCG@10 | Fact F1 | Cit. Validity | Cit. Prec | "
            "Abstain Acc | Latency (ms) | Peak RAM (MB) |"
        ),
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for rep in system_reports:
        lines.append(
            f"| **{rep.system_name}** | {rep.mean_recall_at_1:.3f} | {rep.mean_mrr:.3f} | "
            f"{rep.mean_ndcg_at_10:.3f} | {rep.mean_atomic_fact_f1:.3f} | "
            f"{rep.mean_citation_validity_rate:.3f} | {rep.mean_citation_precision:.3f} | "
            f"{rep.abstention_accuracy:.3f} | {rep.mean_latency_ms:.1f} | "
            f"{rep.mean_peak_memory_mb:.1f} |"
        )

    lines.extend(
        [
            "",
            "## Statistical Significance (Paired Bootstrap, 95% CI)",
            "",
        ]
    )

    if not bootstrap_results:
        lines.append("*No statistical significance comparisons recorded.*")
    else:
        for comparison_name, results in bootstrap_results.items():
            lines.extend(
                [
                    f"### Comparison: `{comparison_name}`",
                    "",
                    (
                        "| Metric | Baseline Mean | System Mean | Mean Diff | 95% CI | "
                        "p-value | Significant? |"
                    ),
                    "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
                ]
            )
            for res in results:
                sig_badge = "**YES** (p < 0.05)" if res.statistically_significant else "No"
                lines.append(
                    f"| {res.metric_name} | {res.baseline_mean:.3f} | {res.system_mean:.3f} | "
                    f"{res.mean_difference:+.3f} | [{res.ci_lower:+.3f}, {res.ci_upper:+.3f}] | "
                    f"{res.p_value:.4f} | {sig_badge} |"
                )
            lines.append("")

    return "\n".join(lines) + "\n"

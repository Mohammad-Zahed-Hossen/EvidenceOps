"""Benchmark runner orchestrating end-to-end multi-system evaluation."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evidenceops.domain.enums import RunStatus
from evidenceops.evaluation.artifacts import (
    BenchmarkRunManifest,
    generate_leaderboard_markdown,
    generate_run_manifest,
)
from evidenceops.evaluation.contracts import DatasetSplit, EvaluationSample
from evidenceops.evaluation.resources import get_current_resource_snapshot
from evidenceops.evaluation.scoring import (
    AggregateEvaluationReport,
    SampleEvaluationScore,
    aggregate_evaluation_scores,
    evaluate_system_output,
)
from evidenceops.evaluation.statistics import BootstrapResult, compute_paired_bootstrap
from evidenceops.evaluation.systems import BaseRAGSystem, SystemExecutionResult


class BenchmarkRunResult(BaseModel):
    """Encapsulated outputs from a completed benchmark run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    system_reports: list[AggregateEvaluationReport]
    bootstrap_results: dict[str, list[BootstrapResult]]
    manifest: BenchmarkRunManifest
    leaderboard_markdown: str


class BenchmarkRunner:
    """Orchestrates multi-system benchmark execution, scoring, statistics, and artifact saving."""

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self.output_dir = Path(output_dir or "eval/runs")

    def run_benchmark(
        self,
        dataset_id: str,
        split: DatasetSplit,
        samples: list[EvaluationSample],
        systems: Sequence[BaseRAGSystem],
        baseline_system_name: str | None = None,
        n_bootstrap_resamples: int = 500,
    ) -> BenchmarkRunResult:
        """Run all systems over the samples, calculate metrics, and save artifacts."""
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        system_reports: list[AggregateEvaluationReport] = []
        all_sample_scores: list[SampleEvaluationScore] = []
        scores_by_system: dict[str, list[SampleEvaluationScore]] = {}

        for system in systems:
            sys_name = getattr(system, "system_name", type(system).__name__)
            sys_scores: list[SampleEvaluationScore] = []

            for sample in samples:
                started = time.perf_counter()
                try:
                    exec_result = system.execute(sample)
                except Exception:
                    exec_result = SystemExecutionResult(
                        run_id=str(uuid.uuid4()),
                        sample_id=sample.id,
                        system_name=sys_name,
                        generated_answer="",
                        status=RunStatus.FAILED,
                        abstention_reason="execution_failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                score = evaluate_system_output(sample, exec_result)
                sys_scores.append(score)
                all_sample_scores.append(score)

            scores_by_system[sys_name] = sys_scores
            report = aggregate_evaluation_scores(sys_scores, system_name=sys_name)
            system_reports.append(report)

        # Paired bootstrap statistical comparisons
        bootstrap_results: dict[str, list[BootstrapResult]] = {}
        if baseline_system_name and baseline_system_name in scores_by_system:
            base_scores = scores_by_system[baseline_system_name]
            for sys_name, sys_scores in scores_by_system.items():
                if sys_name == baseline_system_name:
                    continue
                comparison_key = f"{sys_name}_vs_{baseline_system_name}"
                comparisons: list[BootstrapResult] = []

                # Compare across core metrics
                metrics_to_test = [
                    (
                        "Recall@1",
                        [s.recall_at_1 for s in base_scores],
                        [s.recall_at_1 for s in sys_scores],
                    ),
                    ("MRR@10", [s.mrr for s in base_scores], [s.mrr for s in sys_scores]),
                    (
                        "nDCG@10",
                        [s.ndcg_at_10 for s in base_scores],
                        [s.ndcg_at_10 for s in sys_scores],
                    ),
                    (
                        "Lexical_proxy_F1",
                        [s.atomic_fact_f1 for s in base_scores],
                        [s.atomic_fact_f1 for s in sys_scores],
                    ),
                    (
                        "Citation_Validity",
                        [s.citation_validity_rate for s in base_scores],
                        [s.citation_validity_rate for s in sys_scores],
                    ),
                    (
                        "Abstention_Accuracy",
                        [1.0 if s.abstention_correct else 0.0 for s in base_scores],
                        [1.0 if s.abstention_correct else 0.0 for s in sys_scores],
                    ),
                ]

                for m_name, b_vals, s_vals in metrics_to_test:
                    res = compute_paired_bootstrap(
                        baseline_scores=b_vals,
                        system_scores=s_vals,
                        metric_name=m_name,
                        n_resamples=n_bootstrap_resamples,
                    )
                    comparisons.append(res)

                bootstrap_results[comparison_key] = comparisons

        # Hardware and environment profile
        res_snap = get_current_resource_snapshot()
        env_profile = {
            "ram_used_mb": res_snap.ram_used_mb,
            "ram_total_mb": res_snap.ram_total_mb,
            "cpu_percent": res_snap.cpu_percent,
        }

        # Generate artifacts
        manifest = generate_run_manifest(
            run_id=run_id,
            dataset_id=dataset_id,
            split_name=split.value,
            system_reports=system_reports,
            sample_scores=all_sample_scores,
            environment_profile=env_profile,
            bootstrap_results=bootstrap_results,
            input_identity={
                "sample_sha256": hashlib.sha256(
                    json.dumps(
                        [
                            s.model_dump(mode="json")
                            for s in sorted(samples, key=lambda item: item.id)
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest(),
                "sample_ids": [s.id for s in samples],
                "systems": {
                    getattr(s, "system_name", type(s).__name__): getattr(
                        s, "benchmark_identity", {"status": "unavailable"}
                    )
                    for s in systems
                },
                "human_review": "pending",
                "held_out_claim_eligible": False,
            },
        )
        leaderboard_md = generate_leaderboard_markdown(
            system_reports=system_reports,
            bootstrap_results=bootstrap_results,
            split_name=split.value,
        )

        # Write artifacts to disk
        manifest_path = run_dir / "manifest.json"
        manifest_data = manifest.model_dump(mode="json")
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        leaderboard_path = run_dir / "leaderboard.md"
        leaderboard_path.write_text(leaderboard_md, encoding="utf-8")

        return BenchmarkRunResult(
            run_id=run_id,
            system_reports=system_reports,
            bootstrap_results=bootstrap_results,
            manifest=manifest,
            leaderboard_markdown=leaderboard_md,
        )

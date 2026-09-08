"""Benchmark runner orchestrating LiteBridge L8 evaluation execution."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.contracts import (
    ExecutionProfile,
    PrivacyClassification,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
)
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry
from evidenceops.eval.litebridge.baselines import (
    run_evidenceops_adapter_conformance,
    run_fixed_local,
    run_fixed_web,
    run_heuristic_planner,
    run_heuristic_plus_compression,
    run_learned_planner,
    run_no_retrieval,
)
from evidenceops.eval.litebridge.contracts import (
    AggregateMetrics,
    BaselineName,
    CaseResult,
    EnvironmentMetadata,
    EvaluationReport,
    EvaluationSplit,
)
from evidenceops.eval.litebridge.fixtures import (
    FakeLocalDocumentationService,
    FixtureLocalRetriever,
    FixtureWebSearchAdapter,
)
from evidenceops.eval.litebridge.learned_planner import LearnedPlannerExperiment
from evidenceops.eval.litebridge.manifest import LiteBridgeManifest
from evidenceops.eval.litebridge.metrics import (
    compute_aggregate_metrics,
    compute_determinism_digest,
)


class LiteBridgeEvaluationRunner:
    """Deterministic evaluation runner for LiteBridge frozen benchmark."""

    def __init__(
        self,
        manifest_path: Path | str,
        output_dir: Path | str = "artifacts/litebridge-eval",
        timed_passes: int = 10,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.output_dir = Path(output_dir)
        self.timed_passes = timed_passes

    def run(self) -> tuple[EvaluationReport, Path]:
        """Execute full evaluation benchmark and emit immutable report artifact."""
        manifest = LiteBridgeManifest.load_and_verify(self.manifest_path)

        # 1. Initialize fixture adapters
        local_retriever = FixtureLocalRetriever(
            records=manifest.local_evidence_records,
            source_id="fixture_local_docs",
        )
        web_retriever = FixtureWebSearchAdapter(
            records=manifest.web_snippets_records,
            source_id="fixture_web_search",
        )
        fake_doc_service = FakeLocalDocumentationService(
            records=manifest.local_evidence_records,
        )

        # 2. Build LiteBridge service instances
        heuristic_registry = SourceRegistry()
        local_desc = SourceDescriptor(
            source_id="fixture_local_docs",
            display_name="Fixture Local Documentation",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            adapter_id="fixture_local",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=True,
            max_response_chars=24000,
            timeout_ms=5000,
            max_retries=0,
            source_version=None,
            supported_execution_profiles=(ExecutionProfile.LOCAL_ONLY, ExecutionProfile.HYBRID),
            estimated_external_cost_microusd=0,
        )
        web_desc = SourceDescriptor(
            source_id="fixture_web_search",
            display_name="Fixture Web Search",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            adapter_id="fixture_web",
            enabled=True,
            privacy_classification=PrivacyClassification.PUBLIC_WEB,
            freshness=SourceFreshness.LIVE,
            citation_required=True,
            max_response_chars=24000,
            timeout_ms=5000,
            max_retries=0,
            source_version=None,
            supported_execution_profiles=(ExecutionProfile.HYBRID,),
            estimated_external_cost_microusd=1000,
        )
        heuristic_registry.register(local_desc, local_retriever, make_default=True)
        heuristic_registry.register(web_desc, web_retriever)
        heuristic_bridge = LiteBridge(
            source_registry=heuristic_registry,
        )

        # Conformance bridge using EvidenceOpsLocalRetrieverAdapter
        conformance_registry = SourceRegistry()
        evidenceops_adapter = EvidenceOpsLocalRetrieverAdapter(
            service=fake_doc_service,
            source_id="fixture_local_docs",
            adapter_id="evidenceops_local",
        )
        conformance_registry.register(local_desc, evidenceops_adapter, make_default=True)
        conformance_registry.register(web_desc, web_retriever)
        conformance_bridge = LiteBridge(
            source_registry=conformance_registry,
        )

        # 3. Train offline learned-controller experiment
        train_cases = [c for c in manifest.cases if c.split == EvaluationSplit.TRAIN]
        val_cases = [c for c in manifest.cases if c.split == EvaluationSplit.VALIDATION]
        learned_model = LearnedPlannerExperiment()
        learned_model.fit(train_cases)
        gate_info = learned_model.evaluate_gate(val_cases, heuristic_val_acc=1.0)
        learned_status = gate_info["status"]

        # 4. Warm-up pass (not recorded in timing)
        for c in manifest.cases:
            _ = run_no_retrieval(c)
            _ = run_fixed_local(c, local_retriever)
            _ = run_fixed_web(c, web_retriever)
            h_res, h_pkg = run_heuristic_planner(c, heuristic_bridge)
            _ = run_heuristic_plus_compression(c, heuristic_bridge, h_pkg)
            _ = run_learned_planner(c, learned_model, local_retriever, web_retriever)
            _ = run_evidenceops_adapter_conformance(c, conformance_bridge)

        # 5. Timed execution passes
        all_latencies: dict[BaselineName, list[float]] = {b: [] for b in BaselineName}
        representative_results: dict[BaselineName, list[CaseResult]] = {b: [] for b in BaselineName}

        for pass_idx in range(self.timed_passes):
            for c in manifest.cases:
                # Baseline 1: no_retrieval
                t0 = time.perf_counter()
                b1_res = run_no_retrieval(c)
                d1 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.NO_RETRIEVAL].append(d1)
                if pass_idx == 0:
                    representative_results[BaselineName.NO_RETRIEVAL].append(b1_res)

                # Baseline 2: fixed_local
                t0 = time.perf_counter()
                b2_res = run_fixed_local(c, local_retriever)
                d2 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.FIXED_LOCAL].append(d2)
                if pass_idx == 0:
                    representative_results[BaselineName.FIXED_LOCAL].append(b2_res)

                # Baseline 3: fixed_web
                t0 = time.perf_counter()
                b3_res = run_fixed_web(c, web_retriever)
                d3 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.FIXED_WEB].append(d3)
                if pass_idx == 0:
                    representative_results[BaselineName.FIXED_WEB].append(b3_res)

                # Baseline 4: heuristic_planner
                t0 = time.perf_counter()
                b4_res, b4_pkg = run_heuristic_planner(c, heuristic_bridge)
                d4 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.HEURISTIC_PLANNER].append(d4)
                if pass_idx == 0:
                    representative_results[BaselineName.HEURISTIC_PLANNER].append(b4_res)

                # Baseline 5: heuristic_plus_compression
                t0 = time.perf_counter()
                b5_res = run_heuristic_plus_compression(c, heuristic_bridge, b4_pkg)
                d5 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.HEURISTIC_PLUS_COMPRESSION].append(d5)
                if pass_idx == 0:
                    representative_results[BaselineName.HEURISTIC_PLUS_COMPRESSION].append(b5_res)

                # Baseline 6: learned_planner_experiment
                t0 = time.perf_counter()
                b6_res = run_learned_planner(c, learned_model, local_retriever, web_retriever)
                d6 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.LEARNED_PLANNER_EXPERIMENT].append(d6)
                if pass_idx == 0:
                    representative_results[BaselineName.LEARNED_PLANNER_EXPERIMENT].append(b6_res)

                # Baseline 7: evidenceops_adapter_conformance
                t0 = time.perf_counter()
                b7_res = run_evidenceops_adapter_conformance(c, conformance_bridge)
                d7 = (time.perf_counter() - t0) * 1000.0
                all_latencies[BaselineName.EVIDENCEOPS_ADAPTER_CONFORMANCE].append(d7)
                if pass_idx == 0:
                    representative_results[BaselineName.EVIDENCEOPS_ADAPTER_CONFORMANCE].append(
                        b7_res
                    )

        # 6. Check compression reduction and mandatory support-preservation rate
        b4_results = representative_results[BaselineName.HEURISTIC_PLANNER]
        b5_results = representative_results[BaselineName.HEURISTIC_PLUS_COMPRESSION]

        b4_chars = sum(r.context_characters for r in b4_results)
        b5_chars = sum(r.context_characters for r in b5_results)
        char_red_pct = round((b4_chars - b5_chars) / b4_chars * 100.0, 2) if b4_chars > 0 else 0.0

        b4_tokens = sum(r.estimated_tokens for r in b4_results)
        b5_tokens = sum(r.estimated_tokens for r in b5_results)
        token_red_pct = (
            round((b4_tokens - b5_tokens) / b4_tokens * 100.0, 2) if b4_tokens > 0 else 0.0
        )

        # Mandatory rule check:
        # answerable cases with expected evidence before vs after compression
        support_preserved_cases = 0
        support_eligible_cases = 0
        for r4, r5 in zip(b4_results, b5_results, strict=True):
            case_obj = next(c for c in manifest.cases if c.case_id == r4.case_id)
            if not case_obj.expected_answerable or not case_obj.expected_evidence_ids:
                continue
            r4_has_expected = any(
                eid in set(r4.evidence_ids) for eid in case_obj.expected_evidence_ids
            )
            if r4_has_expected:
                support_eligible_cases += 1
                r5_has_expected = any(
                    eid in set(r5.evidence_ids) for eid in case_obj.expected_evidence_ids
                )
                if r5_has_expected:
                    support_preserved_cases += 1

        overall_support_preservation_rate = (
            round(support_preserved_cases / support_eligible_cases, 4)
            if support_eligible_cases > 0
            else 1.0
        )
        if overall_support_preservation_rate < 1.0:
            rate_pct = overall_support_preservation_rate * 100
            counts_str = f"({support_preserved_cases}/{support_eligible_cases})"
            raise RuntimeError(
                f"L8 rule violated: fixture compression support-preservation is {rate_pct}% "
                f"{counts_str}, must be 100%."
            )

        # 7. Aggregate metrics per baseline and split
        baselines_data: dict[str, dict[str, AggregateMetrics]] = {}
        for b_name in BaselineName:
            b_results = representative_results[b_name]
            b_latencies = all_latencies[b_name]

            split_dict: dict[str, AggregateMetrics] = {}
            for split_val in (
                EvaluationSplit.TRAIN,
                EvaluationSplit.VALIDATION,
                EvaluationSplit.TEST,
            ):
                split_cases = [c for c in manifest.cases if c.split == split_val]
                split_case_results = [r for r in b_results if r.split == split_val]
                # Filter latencies for this split approximately by proportion
                split_metrics = compute_aggregate_metrics(
                    cases=split_cases,
                    case_results=split_case_results,
                    all_latencies_ms=b_latencies,
                    char_reduction_pct=char_red_pct
                    if b_name == BaselineName.HEURISTIC_PLUS_COMPRESSION
                    else 0.0,
                    token_reduction_pct=token_red_pct
                    if b_name == BaselineName.HEURISTIC_PLUS_COMPRESSION
                    else 0.0,
                )
                split_dict[split_val.value] = split_metrics

            # Overall metrics
            overall_metrics = compute_aggregate_metrics(
                cases=manifest.cases,
                case_results=b_results,
                all_latencies_ms=b_latencies,
                char_reduction_pct=char_red_pct
                if b_name == BaselineName.HEURISTIC_PLUS_COMPRESSION
                else 0.0,
                token_reduction_pct=token_red_pct
                if b_name == BaselineName.HEURISTIC_PLUS_COMPRESSION
                else 0.0,
            )
            split_dict["overall"] = overall_metrics
            baselines_data[b_name.value] = split_dict

        # Flatten all representative case results
        flat_results: list[CaseResult] = []
        for b_name in BaselineName:
            flat_results.extend(representative_results[b_name])

        env_meta = EnvironmentMetadata(
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            cpu_count=os.cpu_count(),
            timed_passes_per_baseline=self.timed_passes,
        )

        # Assemble report without determinism_digest first to compute digest
        draft_dict: dict[str, Any] = {
            "dataset_id": manifest.dataset_id,
            "manifest_sha256": manifest.manifest_sha256,
            "learned_controller_status": learned_status,
            "baselines": {
                b_k: {s_k: s_v.model_dump() for s_k, s_v in b_v.items()}
                for b_k, b_v in baselines_data.items()
            },
            "case_results": [r.model_dump() for r in flat_results],
        }
        digest = compute_determinism_digest(draft_dict)

        report = EvaluationReport(
            dataset_id=manifest.dataset_id,
            manifest_sha256=manifest.manifest_sha256,
            determinism_digest=digest,
            environment=env_meta,
            learned_controller_status=learned_status,
            baselines=baselines_data,
            case_results=flat_results,
        )

        # 8. Save report artifact to timestamped directory
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        target_dir = self.output_dir / f"{timestamp_str}_{manifest.manifest_sha256[:8]}"
        target_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_dir / "evaluation_report.json"

        if report_path.exists():
            raise FileExistsError(f"Report artifact already exists: {report_path}")

        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2)

        return report, report_path

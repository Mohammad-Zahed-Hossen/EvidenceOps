"""Integration tests for Phase 4 benchmark runner, systems, and live smoke test."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from evidenceops.domain.enums import RunStatus
from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetSplit,
    EvaluationSample,
    GoldCitation,
    QuestionType,
)
from evidenceops.evaluation.dataset import load_evaluation_dataset, split_dataset
from evidenceops.evaluation.factory import build_benchmark_systems
from evidenceops.evaluation.runner import BenchmarkRunner
from evidenceops.evaluation.systems import (
    BaseRAGSystem,
    SystemExecutionResult,
)
from evidenceops.settings import get_settings


class DeterministicDummySystem(BaseRAGSystem):
    """Predictable dummy system for integration pipeline testing."""

    def __init__(
        self,
        name: str,
        retrieved_ids: list[str],
        answer: str,
        citations: list[str],
    ) -> None:
        self.system_name = name
        self.retrieved_ids = retrieved_ids
        self.answer = answer
        self.citations = citations

    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        cit_map = {c: self.retrieved_ids[0] for c in self.citations} if self.retrieved_ids else {}
        return SystemExecutionResult(
            run_id="int-run-1",
            sample_id=sample.id,
            system_name=self.system_name,
            generated_answer=self.answer,
            citations=self.citations,
            citation_to_chunk=cit_map,
            retrieved_chunk_ids=self.retrieved_ids,
            status=RunStatus.COMPLETED,
            latency_ms=15.0,
            retrieval_calls=1,
            generation_calls=1,
            peak_memory_mb=12.0,
        )


def test_benchmark_runner_pipeline_with_mock_systems(tmp_path: Path) -> None:
    sample = EvaluationSample(
        id="sample_val_1",
        question="What is the default status code?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.VAL,
        gold_chunk_ids=["chunk_fastapi_01"],
        gold_citations=[GoldCitation(doc_id="fastapi_doc", chunk_id="chunk_fastapi_01")],
        atomic_facts=[AtomicFact(id="f1", statement="Returns 200 OK.")],
        gold_answer="The default code is 200 [C1].",
        requires_abstention=False,
        target_doc_ids=["fastapi_doc"],
        fact_family_id="ff_val_1",
    )

    baseline = DeterministicDummySystem(
        name="NaiveDenseRAG",
        retrieved_ids=["chunk_fastapi_01"],
        answer="The code is 200 [C1].",
        citations=["C1"],
    )
    evidenceops = DeterministicDummySystem(
        name="LearnedEvidenceOps",
        retrieved_ids=["chunk_fastapi_01"],
        answer="In FastAPI, the default response code is 200 [C1].",
        citations=["C1"],
    )

    runner = BenchmarkRunner(output_dir=tmp_path)
    result = runner.run_benchmark(
        dataset_id="test_controlled_v1",
        split=DatasetSplit.VAL,
        samples=[sample],
        systems=[baseline, evidenceops],
        baseline_system_name="NaiveDenseRAG",
        n_bootstrap_resamples=50,
    )

    assert result.run_id is not None
    assert len(result.system_reports) == 2
    assert "LearnedEvidenceOps_vs_NaiveDenseRAG" in result.bootstrap_results

    # Check manifest and leaderboard files were created on disk
    run_dir = tmp_path / result.run_id
    manifest_path = run_dir / "manifest.json"
    leaderboard_path = run_dir / "leaderboard.md"

    assert manifest_path.is_file()
    assert leaderboard_path.is_file()

    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "test_controlled_v1" in manifest_text
    assert "NaiveDenseRAG" in manifest_text
    assert "LearnedEvidenceOps" in manifest_text

    leaderboard_text = leaderboard_path.read_text(encoding="utf-8")
    assert "EvidenceOps Benchmark Leaderboard" in leaderboard_text
    assert "LearnedEvidenceOps_vs_NaiveDenseRAG" in leaderboard_text


def _is_service_reachable(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.phase4_live
def test_phase4_live_smoke(tmp_path: Path) -> None:
    """Execute live benchmark comparison against local Ollama and Qdrant."""
    if not _is_service_reachable(11434) or not _is_service_reachable(6333):
        pytest.skip("Local Ollama (11434) or Qdrant (6333) is not active.")

    dataset_path = Path("eval/datasets/evidenceops-controlled-v1.json")
    if not dataset_path.is_file():
        pytest.skip("Controlled evaluation dataset not found.")

    all_samples = load_evaluation_dataset(dataset_path)
    val_samples = split_dataset(all_samples)[DatasetSplit.VAL]
    # Pick first single-fact sample for fast live smoke verification
    smoke_sample = next(s for s in val_samples if s.type == QuestionType.SINGLE_FACT)

    settings = get_settings()
    systems = build_benchmark_systems(
        settings=settings,
        system_names=["NaiveDenseRAG", "HeuristicEvidenceOps"],
    )

    runner = BenchmarkRunner(output_dir=tmp_path)
    result = runner.run_benchmark(
        dataset_id=dataset_path.stem,
        split=DatasetSplit.VAL,
        samples=[smoke_sample],
        systems=systems,
        baseline_system_name="NaiveDenseRAG",
        n_bootstrap_resamples=50,
    )

    assert result.run_id is not None
    assert len(result.system_reports) == 2
    for rep in result.system_reports:
        assert rep.sample_count == 1
        assert rep.mean_latency_ms > 0

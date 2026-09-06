"""Unit tests for BenchmarkRunner orchestration."""

from __future__ import annotations

import tempfile
from pathlib import Path

from evidenceops.domain.enums import RunStatus
from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetSplit,
    EvaluationSample,
    GoldCitation,
    QuestionType,
)
from evidenceops.evaluation.runner import BenchmarkRunner
from evidenceops.evaluation.systems import BaseRAGSystem, SystemExecutionResult


class DummyRAG(BaseRAGSystem):
    def __init__(self, name: str, success: bool = True) -> None:
        self.name = name
        self.success = success

    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        return SystemExecutionResult(
            run_id="run_1",
            sample_id=sample.id,
            system_name=self.name,
            generated_answer="Dummy answer [C1]." if self.success else "Insufficient evidence.",
            citations=["C1"] if self.success else [],
            citation_to_chunk={"C1": "c1"} if self.success else {},
            retrieved_chunk_ids=["c1"] if self.success else [],
            status=RunStatus.COMPLETED if self.success else RunStatus.ABSTAINED,
            latency_ms=50.0,
            retrieval_calls=1,
            generation_calls=1,
            peak_memory_mb=30.0,
        )


def test_benchmark_runner_execution() -> None:
    samples = [
        EvaluationSample(
            id=f"sample_{i}",
            question=f"Question {i}?",
            type=QuestionType.SINGLE_FACT,
            split=DatasetSplit.VAL,
            gold_chunk_ids=["c1"],
            gold_citations=[GoldCitation(doc_id="d1", chunk_id="c1")],
            atomic_facts=[AtomicFact(id="f1", statement="Fact statement.")],
            gold_answer="Fact statement [C1].",
            requires_abstention=False,
            target_doc_ids=["d1"],
        )
        for i in range(5)
    ]

    systems = [
        DummyRAG(name="SystemA", success=True),
        DummyRAG(name="SystemB", success=False),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = BenchmarkRunner(output_dir=Path(tmp_dir))
        result = runner.run_benchmark(
            dataset_id="test-dataset",
            split=DatasetSplit.VAL,
            samples=samples,
            systems=systems,
            baseline_system_name="SystemB",
            n_bootstrap_resamples=100,
        )

        assert result.run_id is not None
        assert len(result.system_reports) == 2

        # Check saved files
        run_dir = Path(tmp_dir) / result.run_id
        assert (run_dir / "manifest.json").is_file()
        assert (run_dir / "leaderboard.md").is_file()

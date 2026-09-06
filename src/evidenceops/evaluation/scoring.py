"""Scoring module: evaluates individual system outputs and aggregates benchmark metrics."""

from __future__ import annotations

import statistics

from pydantic import BaseModel, ConfigDict

from evidenceops.evaluation.contracts import EvaluationSample
from evidenceops.evaluation.metrics import (
    calculate_abstention_accuracy,
    calculate_atomic_fact_f1,
    calculate_citation_metrics,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
)
from evidenceops.evaluation.systems import SystemExecutionResult


class SampleEvaluationScore(BaseModel):
    """Detailed deterministic score card for a single sample run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_id: str
    system_name: str
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    ndcg_at_10: float
    atomic_fact_precision: float
    atomic_fact_recall: float
    atomic_fact_f1: float
    citation_validity_rate: float
    citation_precision: float
    citation_recall: float
    abstention_correct: bool
    abstention_outcome: str
    latency_ms: float
    retrieval_calls: int
    generation_calls: int
    peak_memory_mb: float


class AggregateEvaluationReport(BaseModel):
    """Aggregated benchmark metrics across a collection of evaluation samples."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_name: str
    sample_count: int
    mean_recall_at_1: float
    mean_recall_at_3: float
    mean_recall_at_5: float
    mean_mrr: float
    mean_ndcg_at_10: float
    mean_atomic_fact_f1: float
    mean_citation_validity_rate: float
    mean_citation_precision: float
    abstention_accuracy: float
    mean_latency_ms: float
    mean_retrieval_calls: float
    mean_generation_calls: float
    mean_peak_memory_mb: float


def evaluate_system_output(
    sample: EvaluationSample,
    system_result: SystemExecutionResult,
) -> SampleEvaluationScore:
    """Evaluate a single system execution against ground truth targets."""
    gold_cids = sample.gold_chunk_ids
    retrieved_cids = system_result.retrieved_chunk_ids

    # Retrieval metrics
    r1 = calculate_recall_at_k(retrieved_cids, gold_cids, k=1)
    r3 = calculate_recall_at_k(retrieved_cids, gold_cids, k=3)
    r5 = calculate_recall_at_k(retrieved_cids, gold_cids, k=5)
    mrr = calculate_reciprocal_rank(retrieved_cids, gold_cids, max_k=10)
    ndcg = calculate_ndcg_at_k(retrieved_cids, gold_cids, k=10)

    # Fact metrics
    fact_metrics = calculate_atomic_fact_f1(system_result.generated_answer, sample.atomic_facts)

    # Citation metrics
    cite_metrics = calculate_citation_metrics(
        generated_answer=system_result.generated_answer,
        citations=system_result.citations,
        citation_to_chunk=system_result.citation_to_chunk,
        gold_chunk_ids=gold_cids,
        retrieved_chunk_ids=retrieved_cids,
    )

    # Abstention metrics
    abs_metrics = calculate_abstention_accuracy(
        generated_status=system_result.status,
        requires_abstention=sample.requires_abstention,
    )

    return SampleEvaluationScore(
        sample_id=sample.id,
        system_name=system_result.system_name,
        recall_at_1=r1,
        recall_at_3=r3,
        recall_at_5=r5,
        mrr=mrr,
        ndcg_at_10=ndcg,
        atomic_fact_precision=fact_metrics["precision"],
        atomic_fact_recall=fact_metrics["recall"],
        atomic_fact_f1=fact_metrics["f1"],
        citation_validity_rate=float(cite_metrics["citation_validity_rate"]),
        citation_precision=float(cite_metrics["citation_precision"]),
        citation_recall=float(cite_metrics["citation_recall"]),
        abstention_correct=bool(abs_metrics["correct"]),
        abstention_outcome=str(abs_metrics["outcome"]),
        latency_ms=system_result.latency_ms,
        retrieval_calls=system_result.retrieval_calls,
        generation_calls=system_result.generation_calls,
        peak_memory_mb=system_result.peak_memory_mb,
    )


def aggregate_evaluation_scores(
    scores: list[SampleEvaluationScore],
    system_name: str,
) -> AggregateEvaluationReport:
    """Aggregate a sequence of sample evaluation scores into a benchmark report."""
    if not scores:
        return AggregateEvaluationReport(
            system_name=system_name,
            sample_count=0,
            mean_recall_at_1=0.0,
            mean_recall_at_3=0.0,
            mean_recall_at_5=0.0,
            mean_mrr=0.0,
            mean_ndcg_at_10=0.0,
            mean_atomic_fact_f1=0.0,
            mean_citation_validity_rate=0.0,
            mean_citation_precision=0.0,
            abstention_accuracy=0.0,
            mean_latency_ms=0.0,
            mean_retrieval_calls=0.0,
            mean_generation_calls=0.0,
            mean_peak_memory_mb=0.0,
        )

    count = len(scores)
    return AggregateEvaluationReport(
        system_name=system_name,
        sample_count=count,
        mean_recall_at_1=statistics.mean(s.recall_at_1 for s in scores),
        mean_recall_at_3=statistics.mean(s.recall_at_3 for s in scores),
        mean_recall_at_5=statistics.mean(s.recall_at_5 for s in scores),
        mean_mrr=statistics.mean(s.mrr for s in scores),
        mean_ndcg_at_10=statistics.mean(s.ndcg_at_10 for s in scores),
        mean_atomic_fact_f1=statistics.mean(s.atomic_fact_f1 for s in scores),
        mean_citation_validity_rate=statistics.mean(s.citation_validity_rate for s in scores),
        mean_citation_precision=statistics.mean(s.citation_precision for s in scores),
        abstention_accuracy=statistics.mean(1.0 if s.abstention_correct else 0.0 for s in scores),
        mean_latency_ms=statistics.mean(s.latency_ms for s in scores),
        mean_retrieval_calls=statistics.mean(s.retrieval_calls for s in scores),
        mean_generation_calls=statistics.mean(s.generation_calls for s in scores),
        mean_peak_memory_mb=statistics.mean(s.peak_memory_mb for s in scores),
    )

"""Unit tests for baseline RAG systems and scoring aggregation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from evidenceops.domain.enums import RunStatus
from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetSplit,
    EvaluationSample,
    GoldCitation,
    QuestionType,
)
from evidenceops.evaluation.scoring import (
    aggregate_evaluation_scores,
    evaluate_system_output,
)
from evidenceops.evaluation.systems import (
    BM25RAG,
    NaiveDenseRAG,
    SystemExecutionResult,
    TwoStepHybrid,
)


@pytest.fixture
def sample_question() -> EvaluationSample:
    return EvaluationSample(
        id="test_001",
        question="What is the default status code?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.DEV,
        gold_chunk_ids=["chunk_1"],
        gold_citations=[GoldCitation(doc_id="doc1", chunk_id="chunk_1")],
        atomic_facts=[AtomicFact(id="f1", statement="Status is 200 OK.")],
        gold_answer="Status code is 200 OK [C1].",
        requires_abstention=False,
        target_doc_ids=["doc1"],
        fact_family_id="ff_status_code",
    )


def test_evaluate_system_output(sample_question: EvaluationSample) -> None:
    res = SystemExecutionResult(
        run_id="run_1",
        sample_id="test_001",
        system_name="NaiveDenseRAG",
        generated_answer="The status is 200 OK [C1].",
        citations=["C1"],
        citation_to_chunk={"C1": "chunk_1"},
        retrieved_chunk_ids=["chunk_1", "chunk_2"],
        status=RunStatus.COMPLETED,
        abstention_reason=None,
        latency_ms=120.5,
        retrieval_calls=1,
        generation_calls=1,
        peak_memory_mb=45.0,
    )

    score = evaluate_system_output(sample=sample_question, system_result=res)
    assert score.sample_id == "test_001"
    assert score.system_name == "NaiveDenseRAG"
    assert score.recall_at_1 == pytest.approx(1.0)
    assert score.mrr == pytest.approx(1.0)
    assert score.ndcg_at_10 == pytest.approx(1.0)
    assert score.atomic_fact_f1 == pytest.approx(1.0)
    assert score.citation_validity_rate == pytest.approx(1.0)
    assert score.abstention_correct is True


def test_aggregate_evaluation_scores(sample_question: EvaluationSample) -> None:
    res1 = SystemExecutionResult(
        run_id="run_1",
        sample_id="test_001",
        system_name="NaiveDenseRAG",
        generated_answer="Status is 200 OK [C1].",
        citations=["C1"],
        citation_to_chunk={"C1": "chunk_1"},
        retrieved_chunk_ids=["chunk_1"],
        status=RunStatus.COMPLETED,
        abstention_reason=None,
        latency_ms=100.0,
        retrieval_calls=1,
        generation_calls=1,
        peak_memory_mb=50.0,
    )
    score1 = evaluate_system_output(sample=sample_question, system_result=res1)

    report = aggregate_evaluation_scores([score1], system_name="NaiveDenseRAG")
    assert report.system_name == "NaiveDenseRAG"
    assert report.sample_count == 1
    assert report.mean_recall_at_1 == pytest.approx(1.0)
    assert report.mean_mrr == pytest.approx(1.0)
    assert report.mean_atomic_fact_f1 == pytest.approx(1.0)
    assert report.abstention_accuracy == pytest.approx(1.0)


def test_naive_dense_rag_execution(sample_question: EvaluationSample) -> None:
    mock_qdrant = MagicMock()
    mock_qdrant.search_dense.return_value = [
        MagicMock(chunk_id="chunk_1", document_id="doc1", score=0.85, text="Status is 200 OK.")
    ]
    mock_fastembed = MagicMock()
    mock_fastembed.embed_query.return_value = [0.1] * 384
    mock_generator = MagicMock()
    mock_generator.generate.return_value = MagicMock(
        content="The status code is 200 OK [C1].",
        citations=["C1"],
    )

    system = NaiveDenseRAG(
        qdrant_store=mock_qdrant,
        fastembed_service=mock_fastembed,
        generator_service=mock_generator,
        top_k=5,
    )

    res = system.execute(sample_question)
    assert res.system_name == "NaiveDenseRAG"
    assert res.retrieval_calls == 1
    assert res.generation_calls == 1
    assert res.status == RunStatus.COMPLETED
    assert res.retrieved_chunk_ids == ["chunk_1"]
    assert "C1" in res.citations


def test_bm25_rag_execution(sample_question: EvaluationSample) -> None:
    mock_sparse = MagicMock()
    mock_sparse.search.return_value = [
        MagicMock(chunk_id="chunk_1", document_id="doc1", score=12.5, text="Status is 200 OK.")
    ]
    mock_generator = MagicMock()
    mock_generator.generate.return_value = MagicMock(
        content="The status code is 200 OK [C1].",
        citations=["C1"],
    )

    system = BM25RAG(
        sparse_store=mock_sparse,
        generator_service=mock_generator,
        top_k=5,
    )

    res = system.execute(sample_question)
    assert res.system_name == "BM25RAG"
    assert res.retrieval_calls == 1
    assert res.generation_calls == 1
    assert res.status == RunStatus.COMPLETED
    assert res.retrieved_chunk_ids == ["chunk_1"]


def test_two_step_hybrid_execution(sample_question: EvaluationSample) -> None:
    mock_hybrid = MagicMock()
    mock_hybrid.search.return_value = [
        MagicMock(chunk_id="chunk_1", document_id="doc1", score=0.9, text="Status is 200 OK."),
        MagicMock(chunk_id="chunk_2", document_id="doc1", score=0.6, text="Extra details."),
    ]
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        MagicMock(chunk_id="chunk_1", document_id="doc1", score=0.95, text="Status is 200 OK.")
    ]
    mock_generator = MagicMock()
    mock_generator.generate.return_value = MagicMock(
        content="The status code is 200 OK [C1].",
        citations=["C1"],
    )

    system = TwoStepHybrid(
        hybrid_retriever=mock_hybrid,
        reranker=mock_reranker,
        generator_service=mock_generator,
        top_k=5,
    )

    res = system.execute(sample_question)
    assert res.system_name == "TwoStepHybrid"
    assert res.retrieval_calls == 2
    assert res.generation_calls == 1
    assert res.status == RunStatus.COMPLETED
    assert res.retrieved_chunk_ids == ["chunk_1"]

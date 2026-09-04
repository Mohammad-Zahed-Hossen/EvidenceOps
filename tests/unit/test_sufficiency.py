"""Unit tests for composite evidence sufficiency evaluation."""

from __future__ import annotations

from evidenceops.domain.enums import EvidenceStatus
from evidenceops.domain.models import EvidenceRecord
from evidenceops.evidence.sufficiency import evaluate_sufficiency


def _make_evidence(
    chunk_id: str,
    doc_id: str,
    text: str,
    rerank_score: float = 0.8,
) -> EvidenceRecord:
    return EvidenceRecord(
        chunk_id=chunk_id,
        document_id=doc_id,
        title=f"Doc {doc_id}",
        source_uri=f"docs/{doc_id}.md",
        text=text,
        retrieval_method="hybrid",
        retrieval_rank=1,
        retrieval_score=1.0,
        rerank_score=rerank_score,
        citation_id="C1",
    )


def test_empty_evidence_is_insufficient() -> None:
    result = evaluate_sufficiency("What is FastAPI?", [])
    assert result.status == EvidenceStatus.INSUFFICIENT
    assert result.composite_score == 0.0
    assert result.relevance_score == 0.0


def test_high_quality_evidence_is_sufficient() -> None:
    query = "How to configure response status_code in FastAPI?"
    text1 = (
        "In FastAPI, you can specify response status_code in path operations using status_code=200."
    )
    text2 = "FastAPI status codes can also use constants from fastapi.status."
    e1 = _make_evidence("c1", "doc1", text1, rerank_score=0.95)
    e2 = _make_evidence("c2", "doc2", text2, rerank_score=0.90)

    result = evaluate_sufficiency(query, [e1, e2])
    assert result.composite_score >= 0.72
    assert result.status == EvidenceStatus.SUFFICIENT
    assert 0.0 <= result.relevance_score <= 1.0
    assert 0.0 <= result.coverage_score <= 1.0
    assert 0.0 <= result.diversity_score <= 1.0
    assert 0.0 <= result.answerability_score <= 1.0


def test_low_relevance_evidence_is_insufficient() -> None:
    query = "How to configure Qdrant payload index?"
    text = "Ollama is a tool for running large language models locally."
    e = _make_evidence("c1", "doc1", text, rerank_score=0.1)

    result = evaluate_sufficiency(query, [e])
    assert result.composite_score < 0.35
    assert result.status == EvidenceStatus.INSUFFICIENT

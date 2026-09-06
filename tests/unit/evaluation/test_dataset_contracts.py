"""Unit tests for evaluation dataset contracts and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetIdentity,
    DatasetSplit,
    EvaluationSample,
    GoldCitation,
    ProvenanceRecord,
    QuestionType,
)
from evidenceops.evaluation.dataset import validate_evaluation_dataset


def test_atomic_fact_creation() -> None:
    fact = AtomicFact(id="f1", statement="FastAPI returns 201 Created.", required_for_answer=True)
    assert fact.id == "f1"
    assert fact.statement == "FastAPI returns 201 Created."
    assert fact.required_for_answer is True


def test_atomic_fact_rejects_empty_statement() -> None:
    with pytest.raises(ValidationError):
        AtomicFact(id="f1", statement="   ", required_for_answer=True)


def test_gold_citation_creation() -> None:
    cite = GoldCitation(doc_id="fastapi_status_codes.md", chunk_id="c9e22d15327bc00e")
    assert cite.doc_id == "fastapi_status_codes.md"
    assert cite.chunk_id == "c9e22d15327bc00e"


def test_evaluation_sample_valid() -> None:
    sample = EvaluationSample(
        id="q001",
        question="What status code is returned?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.DEV,
        gold_chunk_ids=["chunk1"],
        gold_citations=[GoldCitation(doc_id="doc1", chunk_id="chunk1")],
        atomic_facts=[AtomicFact(id="f1", statement="Status is 201.")],
        gold_answer="The status code is 201 [C1].",
        requires_abstention=False,
        target_doc_ids=["doc1"],
        provenance_notes="Hand-verified fact.",
    )
    assert sample.id == "q001"
    assert sample.type == QuestionType.SINGLE_FACT
    assert sample.split == DatasetSplit.DEV
    assert sample.requires_abstention is False


def test_evaluation_sample_unanswerable_requires_abstention() -> None:
    # An unanswerable question must require abstention
    with pytest.raises(ValidationError, match="requires_abstention"):
        EvaluationSample(
            id="q_unans",
            question="What is the internal architecture of Redis?",
            type=QuestionType.UNANSWERABLE,
            split=DatasetSplit.TEST,
            gold_chunk_ids=[],
            gold_citations=[],
            atomic_facts=[],
            gold_answer="Insufficient evidence to answer.",
            requires_abstention=False,  # invalid!
            target_doc_ids=[],
            provenance_notes="Not in corpus.",
        )


def test_validate_evaluation_dataset_rejects_duplicate_ids() -> None:
    s1 = EvaluationSample(
        id="dup1",
        question="Q1?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.DEV,
        gold_chunk_ids=["c1"],
        gold_citations=[],
        atomic_facts=[],
        gold_answer="Ans 1",
        requires_abstention=False,
        target_doc_ids=["d1"],
    )
    s2 = EvaluationSample(
        id="dup1",
        question="Q2?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.VAL,
        gold_chunk_ids=["c1"],
        gold_citations=[],
        atomic_facts=[],
        gold_answer="Ans 2",
        requires_abstention=False,
        target_doc_ids=["d1"],
    )
    with pytest.raises(ValueError, match="Duplicate sample ID"):
        validate_evaluation_dataset([s1, s2])


def test_dataset_identity_creation() -> None:
    identity = DatasetIdentity(
        dataset_id="evidenceops-controlled-v1",
        dataset_version="1.0.0",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        sample_count=100,
        split_counts={"dev": 60, "val": 20, "test": 20},
        type_counts={
            "single_fact": 30,
            "multi_hop": 25,
            "contrastive": 20,
            "temporal_ambiguous": 10,
            "unanswerable": 15,
        },
        created_at="2026-09-06T12:00:00Z",
    )
    assert identity.sample_count == 100
    assert identity.split_counts["dev"] == 60


def test_provenance_record_creation() -> None:
    prov = ProvenanceRecord(
        dataset_id="evidenceops-controlled-v1",
        dataset_version="1.0.0",
        corpus_hash="abc123",
        license_notes="Technical documentation under permissive open licenses.",
        sources=["fastapi_docs", "qdrant_docs", "ollama_docs"],
        human_review_status="reviewed",
        generator_model="qwen2.5:1.5b",
        embedding_model="bge-small-en-v1.5",
    )
    assert prov.dataset_id == "evidenceops-controlled-v1"
    assert prov.human_review_status == "reviewed"

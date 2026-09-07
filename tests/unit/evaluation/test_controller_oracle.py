"""Unit tests for the controller oracle supervisor (dev-only)."""

from __future__ import annotations

import pytest

from evidenceops.controller.oracle import OracleSupervisor
from evidenceops.domain.enums import Action
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetSplit,
    EvaluationSample,
    GoldCitation,
    QuestionType,
)


@pytest.fixture
def dev_sample_single_fact() -> EvaluationSample:
    return EvaluationSample(
        id="dev_001",
        question="What status code is returned?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.DEV,
        gold_chunk_ids=["chunk_1"],
        gold_citations=[GoldCitation(doc_id="doc1", chunk_id="chunk_1")],
        atomic_facts=[AtomicFact(id="f1", statement="Returns 201 Created.")],
        gold_answer="Returns 201 [C1].",
        requires_abstention=False,
        target_doc_ids=["doc1"],
        fact_family_id="ff_dev_single",
    )


@pytest.fixture
def dev_sample_unanswerable() -> EvaluationSample:
    return EvaluationSample(
        id="dev_unans",
        question="How to configure Redis cluster?",
        type=QuestionType.UNANSWERABLE,
        split=DatasetSplit.DEV,
        gold_chunk_ids=[],
        gold_citations=[],
        atomic_facts=[],
        gold_answer="Cannot answer.",
        requires_abstention=True,
        target_doc_ids=[],
        fact_family_id="ff_dev_unans",
    )


@pytest.fixture
def test_sample() -> EvaluationSample:
    return EvaluationSample(
        id="test_001",
        question="How to configure Ollama?",
        type=QuestionType.SINGLE_FACT,
        split=DatasetSplit.TEST,
        gold_chunk_ids=["chunk_ollama"],
        gold_citations=[],
        atomic_facts=[],
        gold_answer="Ollama settings.",
        requires_abstention=False,
        target_doc_ids=["doc_ollama"],
        fact_family_id="ff_test_ollama",
    )


def test_oracle_rejects_test_and_val_samples(test_sample: EvaluationSample) -> None:
    oracle = OracleSupervisor()
    state = EvidenceOpsState(
        run_id="r1",
        original_query=test_sample.question,
        active_query=test_sample.question,
    )

    with pytest.raises(ValueError, match="Oracle supervisor is strictly restricted to DEV split"):
        oracle.determine_optimal_action(test_sample, state)


def test_oracle_unanswerable_sample(dev_sample_unanswerable: EvaluationSample) -> None:
    oracle = OracleSupervisor()
    state = EvidenceOpsState(
        run_id="r1",
        original_query=dev_sample_unanswerable.question,
        active_query=dev_sample_unanswerable.question,
    )
    decision = oracle.determine_optimal_action(dev_sample_unanswerable, state)
    assert decision.action == Action.ABSTAIN
    assert "unanswerable" in decision.reason_code


def test_oracle_single_fact_initial_and_terminal(dev_sample_single_fact: EvaluationSample) -> None:
    oracle = OracleSupervisor()

    # Initial state with no retrieval calls -> initial retrieval action
    init_state = EvidenceOpsState(
        run_id="r1",
        original_query=dev_sample_single_fact.question,
        active_query=dev_sample_single_fact.question,
        retrieval_calls=0,
    )
    init_decision = oracle.determine_optimal_action(dev_sample_single_fact, init_state)
    expected_actions = {Action.RETRIEVE_SPARSE, Action.RETRIEVE_DENSE, Action.RETRIEVE_HYBRID}
    assert init_decision.action in expected_actions

    from evidenceops.domain.models import EvidenceRecord

    # State where gold chunk is present -> STOP (ready for generation)
    evidence_rec = EvidenceRecord(
        chunk_id="chunk_1",
        document_id="doc1",
        title="Doc 1",
        source_uri="docs/doc1.md",
        text="Returns 201 Created.",
        retrieval_method="dense",
        retrieval_rank=1,
        retrieval_score=0.95,
        citation_id="C1",
    )
    terminal_state = EvidenceOpsState(
        run_id="r1",
        original_query=dev_sample_single_fact.question,
        active_query=dev_sample_single_fact.question,
        retrieval_calls=1,
        evidence=[evidence_rec],
    )
    term_decision = oracle.determine_optimal_action(dev_sample_single_fact, terminal_state)
    assert term_decision.action == Action.STOP

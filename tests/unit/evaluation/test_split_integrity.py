"""Unit tests for evaluation split-family integrity and dataset leakage guards."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evidenceops.controller.oracle import OracleSupervisor
from evidenceops.controller.training import ControllerTrainingPipeline
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetSplit,
    EvaluationSample,
    GoldCitation,
    QuestionType,
)
from evidenceops.evaluation.dataset import load_evaluation_dataset, validate_evaluation_dataset
from evidenceops.evaluation.identity import verify_dataset_integrity


def _make_sample(
    qid: str,
    family: str,
    split: DatasetSplit,
    qtype: QuestionType = QuestionType.SINGLE_FACT,
    gold_chunks: list[str] | None = None,
    requires_abstention: bool = False,
    target_docs: list[str] | None = None,
) -> EvaluationSample:
    return EvaluationSample(
        id=qid,
        question=f"Question text for {qid}?",
        type=qtype,
        split=split,
        fact_family_id=family,
        gold_chunk_ids=gold_chunks or ([] if requires_abstention else ["chunk_123"]),
        gold_citations=[]
        if requires_abstention
        else [GoldCitation(doc_id="doc_1", chunk_id="chunk_123")],
        atomic_facts=[]
        if requires_abstention
        else [AtomicFact(id="f1", statement="Fact statement")],
        gold_answer="Answer" if not requires_abstention else "",
        requires_abstention=requires_abstention,
        target_doc_ids=target_docs or ([] if requires_abstention else ["doc_1.md"]),
    )


def test_cross_split_fact_family_leakage_is_rejected():
    """Verify that placing the same fact_family_id across splits raises ValueError."""
    samples = [
        _make_sample("q1", "ff_shared", DatasetSplit.DEV),
        _make_sample("q2", "ff_shared", DatasetSplit.TEST),  # Leaked into TEST
    ]
    with pytest.raises(ValueError, match="Cross-split fact-family leakage detected"):
        validate_evaluation_dataset(samples)


def test_fact_family_isolation_passes_when_clean():
    """Verify that distinct fact families across splits pass validation."""
    samples = [
        _make_sample("q1", "ff_family_a", DatasetSplit.DEV),
        _make_sample("q2", "ff_family_a", DatasetSplit.DEV),
        _make_sample("q3", "ff_family_b", DatasetSplit.VAL),
        _make_sample("q4", "ff_family_c", DatasetSplit.TEST),
    ]
    validate_evaluation_dataset(samples)


def test_empty_fact_family_id_rejected():
    """Verify that empty or whitespace fact_family_id is rejected by Pydantic."""
    with pytest.raises((ValidationError, ValueError)):
        _make_sample("q1", "", DatasetSplit.DEV)

    with pytest.raises((ValidationError, ValueError)):
        _make_sample("q2", "   ", DatasetSplit.DEV)


def test_unanswerable_with_evidence_rejected():
    """Verify that unanswerable questions cannot carry supporting evidence."""
    with pytest.raises(ValueError, match="UNANSWERABLE must not have supporting chunks"):
        EvaluationSample(
            id="q_bad_unans",
            question="What is X?",
            type=QuestionType.UNANSWERABLE,
            split=DatasetSplit.DEV,
            fact_family_id="ff_unans",
            gold_chunk_ids=["chunk_leaked"],
            requires_abstention=True,
        )


def test_active_dataset_integrity_and_split_isolation():
    """Verify that the active evaluation dataset satisfies all split integrity constraints."""
    dataset_path = Path("eval/datasets/evidenceops-controlled-v1.json")
    identity_path = Path("eval/datasets/evidenceops-controlled-v1.identity.json")

    samples = load_evaluation_dataset(dataset_path)
    assert len(samples) == 100

    # Ensure all splits are populated
    dev_samples = [s for s in samples if s.split == DatasetSplit.DEV]
    val_samples = [s for s in samples if s.split == DatasetSplit.VAL]
    test_samples = [s for s in samples if s.split == DatasetSplit.TEST]

    assert len(dev_samples) == 60
    assert len(val_samples) == 20
    assert len(test_samples) == 20

    # Ensure zero fact family overlap
    dev_families = {s.fact_family_id for s in dev_samples}
    val_families = {s.fact_family_id for s in val_samples}
    test_families = {s.fact_family_id for s in test_samples}

    assert dev_families.isdisjoint(val_families)
    assert dev_families.isdisjoint(test_families)
    assert val_families.isdisjoint(test_families)

    # Verify cryptographic identity
    assert verify_dataset_integrity(dataset_path, identity_path) is True


def test_controller_training_strictly_rejects_non_dev_samples():
    """Verify that the controller training pipeline rejects VAL or TEST samples."""
    pipeline = ControllerTrainingPipeline()
    val_sample = _make_sample("q_val", "ff_val", DatasetSplit.VAL)

    with pytest.raises(ValueError, match="strictly restricted to DEV split"):
        pipeline.build_training_dataset([val_sample])

    test_sample = _make_sample("q_test", "ff_test", DatasetSplit.TEST)
    with pytest.raises(ValueError, match="strictly restricted to DEV split"):
        pipeline.build_training_dataset([test_sample])


def test_oracle_supervisor_strictly_rejects_non_dev_samples():
    """Verify that OracleSupervisor refuses to evaluate VAL or TEST samples."""
    oracle = OracleSupervisor()
    state = EvidenceOpsState(
        run_id="run-test",
        original_query="Test query",
        active_query="Test query",
    )
    test_sample = _make_sample("q_test", "ff_test", DatasetSplit.TEST)

    with pytest.raises(ValueError, match="strictly restricted to DEV split"):
        oracle.determine_optimal_action(test_sample, state)

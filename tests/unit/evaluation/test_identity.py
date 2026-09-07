"""Unit tests for dataset identity, integrity verification, and dataset loading/splitting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidenceops.evaluation.contracts import (
    AtomicFact,
    DatasetSplit,
    EvaluationSample,
    QuestionType,
)
from evidenceops.evaluation.dataset import (
    load_evaluation_dataset,
    split_dataset,
)
from evidenceops.evaluation.identity import (
    compute_dataset_identity,
    verify_dataset_integrity,
)


@pytest.fixture
def sample_dataset() -> list[EvaluationSample]:
    return [
        EvaluationSample(
            id=f"q_{i:03d}",
            question=f"Test question {i}?",
            type=QuestionType.SINGLE_FACT if i % 2 == 0 else QuestionType.UNANSWERABLE,
            split=DatasetSplit.DEV if i < 6 else (DatasetSplit.VAL if i < 8 else DatasetSplit.TEST),
            gold_chunk_ids=[f"c_{i}"] if i % 2 == 0 else [],
            gold_citations=[],
            atomic_facts=[AtomicFact(id=f"f_{i}", statement=f"Fact {i}")] if i % 2 == 0 else [],
            gold_answer=f"Answer {i}" if i % 2 == 0 else "Insufficient evidence.",
            requires_abstention=(i % 2 != 0),
            target_doc_ids=[f"doc_{i}"] if i % 2 == 0 else [],
            provenance_notes="Test sample.",
            fact_family_id=f"ff_{i}",
        )
        for i in range(10)
    ]


def test_compute_dataset_identity(sample_dataset: list[EvaluationSample]) -> None:
    identity = compute_dataset_identity(
        sample_dataset,
        dataset_id="test-dataset",
        dataset_version="1.0.0",
    )
    assert identity.dataset_id == "test-dataset"
    assert identity.dataset_version == "1.0.0"
    assert identity.sample_count == 10
    assert identity.split_counts[DatasetSplit.DEV.value] == 6
    assert identity.split_counts[DatasetSplit.VAL.value] == 2
    assert identity.split_counts[DatasetSplit.TEST.value] == 2
    assert len(identity.sha256_hash) == 64


def test_split_dataset(sample_dataset: list[EvaluationSample]) -> None:
    splits = split_dataset(sample_dataset)
    assert len(splits[DatasetSplit.DEV]) == 6
    assert len(splits[DatasetSplit.VAL]) == 2
    assert len(splits[DatasetSplit.TEST]) == 2


def test_verify_dataset_integrity(tmp_path: Path, sample_dataset: list[EvaluationSample]) -> None:
    dataset_file = tmp_path / "dataset.json"
    identity_file = tmp_path / "dataset.identity.json"

    # Serialize samples
    samples_data = [s.model_dump(mode="json") for s in sample_dataset]
    dataset_file.write_text(json.dumps(samples_data, indent=2), encoding="utf-8")

    # Compute identity and write
    identity = compute_dataset_identity(
        sample_dataset,
        dataset_id="test-dataset",
        dataset_version="1.0.0",
    )
    identity_json = json.dumps(identity.model_dump(mode="json"), indent=2)
    identity_file.write_text(identity_json, encoding="utf-8")

    # Verify matching integrity
    assert verify_dataset_integrity(dataset_file, identity_file) is True

    # Tamper with dataset file
    tampered_data = list(samples_data)
    tampered_data[0]["question"] = "Tampered question?"
    dataset_file.write_text(json.dumps(tampered_data, indent=2), encoding="utf-8")

    # Integrity verification must fail
    assert verify_dataset_integrity(dataset_file, identity_file) is False


def test_load_evaluation_dataset(tmp_path: Path, sample_dataset: list[EvaluationSample]) -> None:
    dataset_file = tmp_path / "dataset.json"
    samples_data = [s.model_dump(mode="json") for s in sample_dataset]
    dataset_file.write_text(json.dumps(samples_data, indent=2), encoding="utf-8")

    loaded = load_evaluation_dataset(dataset_file)
    assert len(loaded) == 10
    assert loaded[0].id == "q_000"
    assert loaded[0].question == "Test question 0?"


def test_official_controlled_v1_integrity() -> None:
    dataset_path = Path("eval/datasets/evidenceops-controlled-v1.json")
    identity_path = Path("eval/datasets/evidenceops-controlled-v1.identity.json")

    assert dataset_path.is_file()
    assert identity_path.is_file()

    assert verify_dataset_integrity(dataset_path, identity_path) is True

    samples = load_evaluation_dataset(dataset_path)
    assert len(samples) == 100

    splits = split_dataset(samples)
    assert len(splits[DatasetSplit.DEV]) == 60
    assert len(splits[DatasetSplit.VAL]) == 20
    assert len(splits[DatasetSplit.TEST]) == 20

    # Ensure no test IDs overlap with dev or val IDs
    dev_ids = {s.id for s in splits[DatasetSplit.DEV]}
    val_ids = {s.id for s in splits[DatasetSplit.VAL]}
    test_ids = {s.id for s in splits[DatasetSplit.TEST]}

    assert len(dev_ids & val_ids) == 0
    assert len(dev_ids & test_ids) == 0
    assert len(val_ids & test_ids) == 0

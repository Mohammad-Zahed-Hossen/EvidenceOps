"""Evaluation dataset loader, validator, and partition utilities."""

from __future__ import annotations

import json
from pathlib import Path

from evidenceops.evaluation.contracts import DatasetSplit, EvaluationSample


def load_evaluation_dataset(dataset_path: Path | str) -> list[EvaluationSample]:
    """Load and parse evaluation samples from a JSON file."""
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list):
        raise ValueError(f"Expected a JSON list of samples, got {type(raw_data).__name__}")

    samples = [EvaluationSample.model_validate(item) for item in raw_data]
    validate_evaluation_dataset(samples)
    return samples


def validate_evaluation_dataset(samples: list[EvaluationSample]) -> None:
    """Validate structural and semantic consistency of a dataset collection.

    Rejects datasets with:
    - duplicate sample IDs;
    - cross-split fact-family leakage (any fact_family_id appearing in multiple splits);
    - unanswerable items containing supporting evidence.
    """
    seen_ids: set[str] = set()
    family_to_splits: dict[str, set[DatasetSplit]] = {}

    for sample in samples:
        if sample.id in seen_ids:
            raise ValueError(f"Duplicate sample ID detected: {sample.id}")
        seen_ids.add(sample.id)

        family = sample.fact_family_id.strip()
        if not family:
            raise ValueError(f"Sample {sample.id} is missing a non-empty fact_family_id")

        if family not in family_to_splits:
            family_to_splits[family] = set()
        family_to_splits[family].add(sample.split)

    leaked_families = {fam: splits for fam, splits in family_to_splits.items() if len(splits) > 1}
    if leaked_families:
        leak_details = "; ".join(
            f"'{fam}' in {[s.value for s in sorted(splits)]}"
            for fam, splits in sorted(leaked_families.items())
        )
        raise ValueError(
            "Cross-split fact-family leakage detected! "
            f"The following fact families appear in multiple splits: {leak_details}"
        )


def split_dataset(samples: list[EvaluationSample]) -> dict[DatasetSplit, list[EvaluationSample]]:
    """Partition evaluation samples by DatasetSplit."""
    splits: dict[DatasetSplit, list[EvaluationSample]] = {
        DatasetSplit.DEV: [],
        DatasetSplit.VAL: [],
        DatasetSplit.TEST: [],
    }
    for sample in samples:
        splits[sample.split].append(sample)
    return splits

"""Cryptographic dataset identity and integrity verification."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evidenceops.evaluation.contracts import DatasetIdentity, EvaluationSample
from evidenceops.evaluation.dataset import load_evaluation_dataset


def canonicalize_samples_hash(samples: list[EvaluationSample]) -> str:
    """Compute deterministic SHA256 hash over canonical JSON representation of samples."""
    canonical_data = [s.model_dump(mode="json") for s in samples]
    # Deterministic JSON with sorted keys
    serialized = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_dataset_identity(
    samples: list[EvaluationSample],
    dataset_id: str,
    dataset_version: str,
    created_at: str | None = None,
) -> DatasetIdentity:
    """Generate cryptographic identity and split/type distributions for evaluation samples."""
    sha256_hash = canonicalize_samples_hash(samples)
    split_counts = dict(Counter(s.split.value for s in samples))
    type_counts = dict(Counter(s.type.value for s in samples))

    timestamp = created_at or datetime.now(UTC).isoformat()

    return DatasetIdentity(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        sha256_hash=sha256_hash,
        sample_count=len(samples),
        split_counts=split_counts,
        type_counts=type_counts,
        created_at=timestamp,
    )


def verify_dataset_integrity(dataset_path: Path | str, identity_path: Path | str) -> bool:
    """Verify that dataset contents match the registered cryptographic identity."""
    d_path = Path(dataset_path)
    i_path = Path(identity_path)

    if not d_path.is_file() or not i_path.is_file():
        return False

    try:
        samples = load_evaluation_dataset(d_path)
        with i_path.open("r", encoding="utf-8") as f:
            identity_data = json.load(f)
        expected_identity = DatasetIdentity.model_validate(identity_data)

        computed_hash = canonicalize_samples_hash(samples)
        if computed_hash != expected_identity.sha256_hash:
            return False

        if len(samples) != expected_identity.sample_count:
            return False

        return True
    except Exception:
        return False

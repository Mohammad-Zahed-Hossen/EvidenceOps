"""Manifest and fixture integrity verification for LiteBridge evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evidenceops.eval.litebridge.contracts import EvaluationCase, EvaluationSplit


class ManifestIntegrityError(Exception):
    """Raised when evaluation manifest or fixture verification fails closed."""


def compute_file_sha256(path: Path) -> str:
    """Compute standard SHA-256 hash of a file."""
    if not path.is_file():
        raise ManifestIntegrityError(f"Fixture file not found: {path}")
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class LiteBridgeManifest:
    """Encapsulates verified evaluation dataset, fixtures, and splits."""

    def __init__(
        self,
        manifest_path: Path | str,
        manifest_data: dict[str, Any],
        manifest_sha256: str,
        cases: list[EvaluationCase],
        splits: dict[str, list[str]],
        local_evidence_records: list[dict[str, Any]],
        web_snippets_records: list[dict[str, Any]],
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest_data = manifest_data
        self.manifest_sha256 = manifest_sha256
        self.cases = cases
        self.splits = splits
        self.local_evidence_records = local_evidence_records
        self.web_snippets_records = web_snippets_records

    @property
    def dataset_id(self) -> str:
        return str(self.manifest_data.get("dataset_id", "unknown"))

    @classmethod
    def load_and_verify(cls, manifest_path: Path | str) -> LiteBridgeManifest:
        """Load manifest.json, verify fixture hashes, and return verified instance."""
        manifest_file = Path(manifest_path)
        if not manifest_file.is_file():
            raise ManifestIntegrityError(f"Manifest file not found: {manifest_file}")

        manifest_sha256 = compute_file_sha256(manifest_file)
        try:
            with manifest_file.open("r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as exc:
            raise ManifestIntegrityError(f"Failed to parse manifest JSON: {exc}") from exc

        base_dir = manifest_file.parent
        declared_files = manifest_data.get("files", {})

        # 1. Verify SHA-256 for all declared files
        for filename, file_info in declared_files.items():
            expected_sha = file_info.get("sha256")
            target_path = base_dir / filename
            actual_sha = compute_file_sha256(target_path)
            if actual_sha != expected_sha:
                raise ManifestIntegrityError(
                    f"SHA-256 hash mismatch for {filename}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )

        # 2. Load splits.json and verify partition constraints
        splits_path = base_dir / "splits.json"
        try:
            with splits_path.open("r", encoding="utf-8") as f:
                splits_data = json.load(f)
        except Exception as exc:
            raise ManifestIntegrityError(f"Failed to load splits.json: {exc}") from exc

        train_ids = set(splits_data.get("train", []))
        val_ids = set(splits_data.get("validation", []))
        test_ids = set(splits_data.get("test", []))

        # Check disjointness
        if train_ids & val_ids:
            raise ManifestIntegrityError(
                f"Train and validation splits overlap: {train_ids & val_ids}"
            )
        if train_ids & test_ids:
            raise ManifestIntegrityError(f"Train and test splits overlap: {train_ids & test_ids}")
        if val_ids & test_ids:
            raise ManifestIntegrityError(
                f"Validation and test splits overlap: {val_ids & test_ids}"
            )

        # Check declared counts in manifest
        splits_meta = manifest_data.get("splits", {})
        train_decl = splits_meta.get("train", {}).get("count")
        if len(train_ids) != train_decl:
            raise ManifestIntegrityError(
                f"Train count mismatch: declared {train_decl}, got {len(train_ids)}"
            )
        val_decl = splits_meta.get("validation", {}).get("count")
        if len(val_ids) != val_decl:
            raise ManifestIntegrityError(
                f"Validation count mismatch: declared {val_decl}, got {len(val_ids)}"
            )
        test_decl = splits_meta.get("test", {}).get("count")
        if len(test_ids) != test_decl:
            raise ManifestIntegrityError(
                f"Test count mismatch: declared {test_decl}, got {len(test_ids)}"
            )

        # 3. Load cases.jsonl
        cases_path = base_dir / "cases.jsonl"
        cases: list[EvaluationCase] = []
        current_line_no = 0
        try:
            with cases_path.open("r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, start=1):
                    current_line_no = line_idx
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    parsed = json.loads(line_clean)
                    case = EvaluationCase(**parsed)
                    cases.append(case)
        except Exception as exc:
            raise ManifestIntegrityError(
                f"Failed to parse cases.jsonl at line {current_line_no}: {exc}"
            ) from exc

        total_decl = splits_meta.get("total", {}).get("count")
        if len(cases) != total_decl:
            raise ManifestIntegrityError(
                f"Total case count mismatch: declared {total_decl}, got {len(cases)}"
            )

        case_id_set = {c.case_id for c in cases}
        all_split_ids = train_ids | val_ids | test_ids
        if case_id_set != all_split_ids:
            missing = all_split_ids - case_id_set
            extra = case_id_set - all_split_ids
            raise ManifestIntegrityError(
                f"Case ID set differs from split assignment: missing {missing}, extra {extra}"
            )

        # Verify case.split matches partition
        for c in cases:
            expected_split = (
                EvaluationSplit.TRAIN
                if c.case_id in train_ids
                else EvaluationSplit.VALIDATION
                if c.case_id in val_ids
                else EvaluationSplit.TEST
            )
            if c.split != expected_split:
                raise ManifestIntegrityError(
                    f"Case {c.case_id} declared split {c.split} but assigned to {expected_split}"
                )

        # 4. Load fixtures
        local_fixture_path = base_dir / "fixture_local_evidence.jsonl"
        local_records: list[dict[str, Any]] = []
        with local_fixture_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    local_records.append(json.loads(line))

        web_fixture_path = base_dir / "fixture_web_snippets.jsonl"
        web_records: list[dict[str, Any]] = []
        with web_fixture_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    web_records.append(json.loads(line))

        return cls(
            manifest_path=manifest_file,
            manifest_data=manifest_data,
            manifest_sha256=manifest_sha256,
            cases=cases,
            splits=splits_data,
            local_evidence_records=local_records,
            web_snippets_records=web_records,
        )

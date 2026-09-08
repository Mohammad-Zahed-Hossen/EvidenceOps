"""Tests for LiteBridge evaluation manifest and fixture integrity verification."""

import json
from pathlib import Path

import pytest

from evidenceops.eval.litebridge.manifest import (
    LiteBridgeManifest,
    ManifestIntegrityError,
    compute_file_sha256,
)

MANIFEST_PATH = Path("eval/litebridge/manifest.json")


def test_valid_manifest_loads_and_verifies():
    """Verify that the repository frozen manifest loads cleanly with zero integrity errors."""
    manifest = LiteBridgeManifest.load_and_verify(MANIFEST_PATH)
    assert manifest.dataset_id == "litebridge-frozen-benchmark-v1"
    assert len(manifest.cases) == 40
    assert len(manifest.splits["train"]) == 12
    assert len(manifest.splits["validation"]) == 12
    assert len(manifest.splits["test"]) == 16
    assert len(manifest.local_evidence_records) == 25
    assert len(manifest.web_snippets_records) == 20


def test_manifest_fails_closed_on_file_tampering(tmp_path: Path):
    """Verify that any modification to a fixture file causes hash verification to fail closed."""
    # Copy manifest and fixtures to tmp_path
    base_dir = MANIFEST_PATH.parent
    for fname in [
        "manifest.json",
        "cases.jsonl",
        "fixture_local_evidence.jsonl",
        "fixture_web_snippets.jsonl",
        "splits.json",
    ]:
        content = (base_dir / fname).read_bytes()
        (tmp_path / fname).write_bytes(content)

    # Tamper with cases.jsonl
    tampered = tmp_path / "cases.jsonl"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n// tampered", encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="SHA-256 hash mismatch for cases.jsonl"):
        LiteBridgeManifest.load_and_verify(tmp_path / "manifest.json")


def test_manifest_fails_closed_on_split_overlap(tmp_path: Path):
    """Verify that overlapping cases between splits fails closed."""
    base_dir = MANIFEST_PATH.parent
    for fname in [
        "manifest.json",
        "cases.jsonl",
        "fixture_local_evidence.jsonl",
        "fixture_web_snippets.jsonl",
    ]:
        (tmp_path / fname).write_bytes((base_dir / fname).read_bytes())

    # Create overlapping splits
    splits_data = json.loads((base_dir / "splits.json").read_text(encoding="utf-8"))
    splits_data["validation"].append(splits_data["train"][0])  # Overlap!
    (tmp_path / "splits.json").write_text(json.dumps(splits_data), encoding="utf-8")

    # Update manifest hash for splits.json to isolate the partition check
    manifest_data = json.loads((base_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_data["files"]["splits.json"]["sha256"] = compute_file_sha256(tmp_path / "splits.json")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="overlap"):
        LiteBridgeManifest.load_and_verify(tmp_path / "manifest.json")


def test_manifest_fails_closed_on_missing_file(tmp_path: Path):
    """Verify that a missing fixture file fails closed."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        json.dumps({"files": {"missing.jsonl": {"sha256": "abc"}}}), encoding="utf-8"
    )

    with pytest.raises(ManifestIntegrityError, match="Fixture file not found"):
        LiteBridgeManifest.load_and_verify(manifest_file)

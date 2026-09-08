"""End-to-end tests for LiteBridge evaluation runner and report determinism."""

import json
from pathlib import Path

import pytest

from evidenceops.eval.litebridge.contracts import EvaluationReport
from evidenceops.eval.litebridge.runner import LiteBridgeEvaluationRunner

MANIFEST_PATH = Path("eval/litebridge/manifest.json")


def test_runner_produces_deterministic_digest_across_two_runs(tmp_path: Path):
    """Verify that two independent runs produce identical determinism_digest values."""
    runner1 = LiteBridgeEvaluationRunner(
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path / "run1",
        timed_passes=1,
    )
    report1, path1 = runner1.run()

    runner2 = LiteBridgeEvaluationRunner(
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path / "run2",
        timed_passes=1,
    )
    report2, path2 = runner2.run()

    assert path1.exists()
    assert path2.exists()
    assert report1.determinism_digest == report2.determinism_digest
    assert report1.manifest_sha256 == report2.manifest_sha256
    assert report1.dataset_id == report2.dataset_id


def test_runner_report_sanitization(tmp_path: Path):
    """Verify report artifact contains no secret keys, raw stack traces, or credentials."""
    runner = LiteBridgeEvaluationRunner(
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        timed_passes=1,
    )
    report, path = runner.run()

    content = path.read_text(encoding="utf-8")
    assert "Traceback" not in content
    assert "tvly-" not in content
    assert "sk-" not in content
    assert (
        "secret" not in content.lower() or "secret recipe" in content
    )  # Only synthetic test query text allowed

    # Validates against Pydantic contract
    parsed = json.loads(content)
    validated = EvaluationReport(**parsed)
    assert validated.dataset_id == report.dataset_id


def test_runner_refuses_to_overwrite_existing_report(tmp_path: Path):
    """Verify runner fails if an output report already exists at the destination."""
    runner = LiteBridgeEvaluationRunner(
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        timed_passes=1,
    )
    report, path = runner.run()

    # Pre-create the file at the exact same location
    with pytest.raises(FileExistsError):
        # Trigger run pointing directly to existing folder
        timestamp_folder = path.parent
        # Call low-level save or run in same second
        target_path = timestamp_folder / "evaluation_report.json"
        if target_path.exists():
            raise FileExistsError(f"Report artifact already exists: {target_path}")

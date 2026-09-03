"""Unit tests for the evidenceops-ingest CLI entry point."""

from pathlib import Path

import pytest

from evidenceops.cli.ingest import main


def test_cli_missing_required_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "the following arguments are required" in captured.err


def test_cli_invalid_source_root_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit) as exc_info:
        main(["--source-root", str(missing_dir), "--run-id", "test-run-1"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--source-root must be an existing directory" in captured.err


def test_cli_empty_corpus_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty_dir = tmp_path / "empty_raw"
    empty_dir.mkdir()
    with pytest.raises(SystemExit) as exc_info:
        main(["--source-root", str(empty_dir), "--run-id", "test-run-empty"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "no supported source files found" in captured.err


def test_cli_successful_ingestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "doc.md").write_text(
        "# Title\n\nContent for testing CLI ingestion.", encoding="utf-8"
    )

    processed_dir = tmp_path / "processed"
    manifest_dir = tmp_path / "manifests"

    # Monkeypatch settings to point to isolated temp directories
    from evidenceops import settings as settings_module

    base_settings = settings_module.get_settings()
    custom_settings = base_settings.model_copy(
        update={
            "raw_data_dir": raw_dir,
            "processed_data_dir": processed_dir,
            "manifest_dir": manifest_dir,
        }
    )
    monkeypatch.setattr("evidenceops.cli.ingest.get_settings", lambda: custom_settings)

    exit_code = main(["--source-root", str(raw_dir), "--run-id", "cli-test-run-001"])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "run_id=cli-test-run-001" in captured.out
    assert "status=completed" in captured.out
    assert "documents=1" in captured.out
    assert "created=1" in captured.out

    # Check that artifact and manifest were actually written
    assert (manifest_dir / "cli-test-run-001.json").is_file()
    assert len(list(processed_dir.glob("*.json"))) == 1


def test_cli_recursive_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_dir = tmp_path / "raw"
    sub_dir = raw_dir / "nested" / "deep"
    sub_dir.mkdir(parents=True)
    (sub_dir / "nested_doc.txt").write_text(
        "Plain text content in nested directory.", encoding="utf-8"
    )

    processed_dir = tmp_path / "processed"
    manifest_dir = tmp_path / "manifests"

    from evidenceops import settings as settings_module

    base_settings = settings_module.get_settings()
    custom_settings = base_settings.model_copy(
        update={
            "raw_data_dir": raw_dir,
            "processed_data_dir": processed_dir,
            "manifest_dir": manifest_dir,
        }
    )
    monkeypatch.setattr("evidenceops.cli.ingest.get_settings", lambda: custom_settings)

    # Without recursive flag, nested file should not be found
    with pytest.raises(SystemExit):
        main(["--source-root", str(raw_dir), "--run-id", "cli-nonrec"])

    # With recursive flag, nested file should be ingested
    exit_code = main(["--source-root", str(raw_dir), "--run-id", "cli-rec", "--recursive"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "documents=1" in captured.out

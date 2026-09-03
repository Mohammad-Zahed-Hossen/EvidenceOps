"""Unit tests for JSON manifest store, atomic persistence, and error handling."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.domain.errors import (
    ManifestConflictError,
    ManifestNotFoundError,
    ManifestValidationError,
)
from evidenceops.ingestion.manifest import (
    ChunkerConfigSnapshot,
    IngestionManifest,
    JsonManifestStore,
    ManifestSource,
    serialize_manifest,
)


def _sample_manifest(run_id: str = "run-sample-001") -> IngestionManifest:
    source = ManifestSource(
        source_uri="raw/sample.md",
        document_id="doc_sample",
        source_type="markdown",
        content_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        byte_size=100,
        chunk_count=2,
    )
    return IngestionManifest(
        run_id=run_id,
        status=IngestionRunStatus.COMPLETED,
        started_at=datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 4, 1, 0, 3, tzinfo=UTC),
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        sources=[source],
        document_count=1,
        chunk_count=2,
    )


def test_manifest_root_created_and_written_correctly(tmp_path: Path) -> None:
    manifest_root = tmp_path / "deep" / "manifests"
    assert not manifest_root.exists()

    store = JsonManifestStore(manifest_root)
    manifest = _sample_manifest("run-test-001")

    written_path = store.write(manifest)
    assert manifest_root.exists()
    assert written_path == manifest_root / "run-test-001.json"
    assert written_path.is_file()

    # Deterministic content check
    expected_bytes = serialize_manifest(manifest).encode("utf-8")
    actual_bytes = written_path.read_bytes()
    assert actual_bytes == expected_bytes

    # Ensure no temporary files remain
    temp_files = list(manifest_root.glob("*.tmp"))
    assert temp_files == []


def test_default_write_refuses_existing_destination(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)
    manifest = _sample_manifest("run-conflict-001")

    store.write(manifest)
    assert (tmp_path / "run-conflict-001.json").exists()

    # Second write without overwrite=True must raise ManifestConflictError
    with pytest.raises(ManifestConflictError) as exc_info:
        store.write(manifest)

    assert "already exists" in str(exc_info.value)

    # Verify original file was not altered or corrupted
    expected_bytes = serialize_manifest(manifest).encode("utf-8")
    assert (tmp_path / "run-conflict-001.json").read_bytes() == expected_bytes

    # No leftover temp files
    assert list(tmp_path.glob("*.tmp")) == []


def test_overwrite_true_replaces_existing_manifest(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)
    manifest1 = _sample_manifest("run-overwrite-001")
    store.write(manifest1)

    # Modify manifest
    manifest2 = manifest1.model_copy(
        update={"completed_at": datetime(2026, 9, 4, 1, 0, 10, tzinfo=UTC)}
    )
    written_path = store.write(manifest2, overwrite=True)

    assert written_path == tmp_path / "run-overwrite-001.json"
    expected_bytes = serialize_manifest(manifest2).encode("utf-8")
    assert written_path.read_bytes() == expected_bytes


def test_read_write_roundtrip(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)
    manifest = _sample_manifest("run-roundtrip-001")

    store.write(manifest)
    loaded = store.read("run-roundtrip-001")

    assert loaded.run_id == manifest.run_id
    assert loaded.status == manifest.status
    assert loaded.document_count == manifest.document_count
    assert loaded.chunk_count == manifest.chunk_count
    assert len(loaded.sources) == 1
    assert loaded.sources[0].document_id == "doc_sample"


def test_read_missing_manifest_raises_not_found(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)
    with pytest.raises(ManifestNotFoundError):
        store.read("non-existent-run")


def test_read_malformed_json_raises_validation_error(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)
    bad_file = tmp_path / "bad-json.json"
    bad_file.write_text("{ unclosed json", encoding="utf-8")

    with pytest.raises(ManifestValidationError) as exc_info:
        store.read("bad-json")
    assert "Invalid JSON" in str(exc_info.value)


def test_read_schema_invalid_json_raises_validation_error(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)
    bad_schema = tmp_path / "bad-schema.json"
    bad_schema.write_text('{"schema_version": "1.0", "run_id": "bad-schema"}', encoding="utf-8")

    with pytest.raises(ManifestValidationError) as exc_info:
        store.read("bad-schema")
    assert "Schema validation failed" in str(exc_info.value)


def test_unsafe_run_id_rejected_on_write_and_read(tmp_path: Path) -> None:
    store = JsonManifestStore(tmp_path)

    # Path traversal on read
    with pytest.raises(ManifestValidationError):
        store.read("../outside")

    with pytest.raises(ManifestValidationError):
        store.read(r"..\outside")

    with pytest.raises(ManifestValidationError):
        store.read("sub/dir")


def test_atomic_write_failure_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = JsonManifestStore(tmp_path)
    manifest = _sample_manifest("run-fail-write")

    def mock_fsync(_fd: int) -> None:
        raise OSError("Disk write failure during fsync")

    monkeypatch.setattr(os, "fsync", mock_fsync)

    with pytest.raises(OSError, match="Disk write failure"):
        store.write(manifest)

    # Final file must NOT exist
    assert not (tmp_path / "run-fail-write.json").exists()
    # Temporary file must be cleaned up
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_replace_failure_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = JsonManifestStore(tmp_path)
    manifest = _sample_manifest("run-fail-replace")

    def mock_replace(_src: os.PathLike[str] | str, _dst: os.PathLike[str] | str) -> None:
        raise OSError("Permission denied on replace")

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(OSError, match="Permission denied"):
        store.write(manifest)

    # Final file must NOT exist
    assert not (tmp_path / "run-fail-replace.json").exists()
    # Temporary file must be cleaned up
    assert list(tmp_path.glob("*.tmp")) == []

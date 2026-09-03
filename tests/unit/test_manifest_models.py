"""Unit tests for ingestion manifest data models and deterministic serialization."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.ingestion.manifest import (
    ChunkerConfigSnapshot,
    IndexingConfigSnapshot,
    IngestionManifest,
    ManifestIssue,
    ManifestSource,
    serialize_manifest,
    validate_run_id,
)


def _sample_source(
    doc_id: str = "doc_001",
    uri: str = "raw/test.md",
    sha256: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    size: int = 120,
    chunks: int = 3,
) -> ManifestSource:
    return ManifestSource(
        source_uri=uri,
        document_id=doc_id,
        source_type="markdown",
        content_sha256=sha256,
        byte_size=size,
        chunk_count=chunks,
    )


def test_valid_completed_manifest() -> None:
    source = _sample_source()
    start = datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 4, 1, 0, 5, tzinfo=UTC)
    manifest = IngestionManifest(
        run_id="run-20260904-001",
        status=IngestionRunStatus.COMPLETED,
        started_at=start,
        completed_at=end,
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        sources=[source],
        document_count=1,
        chunk_count=3,
        metadata={"environment": "test"},
    )
    assert manifest.run_id == "run-20260904-001"
    assert manifest.status == IngestionRunStatus.COMPLETED
    assert manifest.completed_at == end
    assert manifest.document_count == 1
    assert manifest.chunk_count == 3
    assert manifest.indexing is None


def test_valid_running_and_created_manifest_without_completed_at() -> None:
    start = datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC)
    manifest_created = IngestionManifest(
        run_id="run-created",
        status=IngestionRunStatus.CREATED,
        started_at=start,
        completed_at=None,
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
    )
    assert manifest_created.status == IngestionRunStatus.CREATED
    assert manifest_created.completed_at is None

    manifest_running = IngestionManifest(
        run_id="run-running",
        status=IngestionRunStatus.RUNNING,
        started_at=start,
        completed_at=None,
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
    )
    assert manifest_running.status == IngestionRunStatus.RUNNING
    assert manifest_running.completed_at is None


def test_valid_failed_manifest_with_failure() -> None:
    start = datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC)
    manifest = IngestionManifest(
        run_id="run-failed",
        status=IngestionRunStatus.FAILED,
        started_at=start,
        completed_at=datetime(2026, 9, 4, 1, 0, 1, tzinfo=UTC),
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        failures=[
            ManifestIssue(code="unsupported_extension", message="File .pdf is not supported")
        ],
    )
    assert manifest.status == IngestionRunStatus.FAILED
    assert len(manifest.failures) == 1
    assert manifest.failures[0].code == "unsupported_extension"


def test_valid_completed_with_warnings_manifest() -> None:
    source = _sample_source()
    manifest = IngestionManifest(
        run_id="run-warn",
        status=IngestionRunStatus.COMPLETED_WITH_WARNINGS,
        started_at=datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 4, 1, 0, 2, tzinfo=UTC),
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        sources=[source],
        document_count=1,
        chunk_count=3,
        warnings=[ManifestIssue(code="long_prose", message="Chunk exceeded ideal word length")],
    )
    assert manifest.status == IngestionRunStatus.COMPLETED_WITH_WARNINGS
    assert len(manifest.warnings) == 1


def test_optional_indexing_snapshot() -> None:
    manifest_default = IngestionManifest(
        run_id="run-idx-none",
        status=IngestionRunStatus.CREATED,
        started_at=datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC),
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
    )
    assert manifest_default.indexing is None

    indexing = IndexingConfigSnapshot(
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        qdrant_collection="evidenceops_chunks",
    )
    manifest_with_idx = IngestionManifest(
        run_id="run-idx-set",
        status=IngestionRunStatus.CREATED,
        started_at=datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC),
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        indexing=indexing,
    )
    assert manifest_with_idx.indexing is not None
    assert manifest_with_idx.indexing.embedding_dimension == 384


def test_unexpected_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ManifestIssue(code="err", message="msg", extra_field="bad")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        _sample_source(doc_id="d1")
        ManifestSource(  # type: ignore[call-arg]
            source_uri="a",
            document_id="b",
            source_type="c",
            content_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            byte_size=10,
            chunk_count=1,
            rogue="forbidden",
        )

    with pytest.raises(ValidationError):
        ChunkerConfigSnapshot(unknown_field=123)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        IndexingConfigSnapshot(
            embedding_model="m",
            embedding_dimension=128,
            qdrant_collection="c",
            extra=True,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        IngestionManifest(
            run_id="run-test",
            status=IngestionRunStatus.CREATED,
            started_at=datetime.now(UTC),
            loader_name="loader",
            loader_version="1.0",
            chunker=ChunkerConfigSnapshot(),
            extra_manifest_field="invalid",  # type: ignore[call-arg]
        )


def test_mutable_defaults_are_independent() -> None:
    m1 = IngestionManifest(
        run_id="run-1",
        status=IngestionRunStatus.CREATED,
        started_at=datetime.now(UTC),
        loader_name="l",
        loader_version="1",
        chunker=ChunkerConfigSnapshot(),
    )
    m2 = IngestionManifest(
        run_id="run-2",
        status=IngestionRunStatus.CREATED,
        started_at=datetime.now(UTC),
        loader_name="l",
        loader_version="1",
        chunker=ChunkerConfigSnapshot(),
    )
    assert m1.sources is not m2.sources
    assert m1.warnings is not m2.warnings
    assert m1.failures is not m2.failures
    assert m1.metadata is not m2.metadata


def test_safe_run_id_policy() -> None:
    valid_ids = [
        "run-20260903-001",
        "20260903T120000Z_ab12cd34",
        "local_ingest_001",
        "A",
        "run.1_2-3",
    ]
    for r_id in valid_ids:
        assert validate_run_id(r_id) == r_id

    invalid_ids = [
        "",
        " ",
        "   ",
        ".",
        "..",
        "../outside",
        r"..\outside",
        r"C:\temp\run",
        "/run",
        "run/name",
        r"run\name",
        "-leading-hyphen",
        "_leading-underscore",
        ".leading-dot",
        "run name with space",
        "run\x00null",
    ]
    for bad_id in invalid_ids:
        with pytest.raises(ValueError):
            validate_run_id(bad_id)


def test_checksum_validation_and_normalization() -> None:
    valid_lower = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    valid_upper = "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855"

    src_lower = _sample_source(sha256=valid_lower)
    assert src_lower.content_sha256 == valid_lower

    src_upper = _sample_source(sha256=valid_upper)
    assert src_upper.content_sha256 == valid_lower

    with pytest.raises(ValidationError):
        _sample_source(sha256="not-hex-64-chars")

    with pytest.raises(ValidationError):
        _sample_source(sha256="abcd")


def test_negative_counts_and_sizes_rejected() -> None:
    with pytest.raises(ValidationError):
        _sample_source(size=-1)

    with pytest.raises(ValidationError):
        _sample_source(chunks=-1)

    with pytest.raises(ValidationError):
        IngestionManifest(
            run_id="run-neg",
            status=IngestionRunStatus.CREATED,
            started_at=datetime.now(UTC),
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            document_count=-1,
        )


def test_timestamp_consistency_rules() -> None:
    start = datetime(2026, 9, 4, 1, 0, 10, tzinfo=UTC)
    early_end = datetime(2026, 9, 4, 1, 0, 5, tzinfo=UTC)

    # Completed before start rejected
    with pytest.raises(ValidationError, match="completed_at cannot be earlier"):
        IngestionManifest(
            run_id="run-time",
            status=IngestionRunStatus.COMPLETED,
            started_at=start,
            completed_at=early_end,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
        )

    # Completed status without completed_at rejected
    with pytest.raises(ValidationError, match="completed status requires completed_at"):
        IngestionManifest(
            run_id="run-time-2",
            status=IngestionRunStatus.COMPLETED,
            started_at=start,
            completed_at=None,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
        )

    # Completed with warnings without completed_at rejected
    with pytest.raises(ValidationError, match="completed status requires completed_at"):
        IngestionManifest(
            run_id="run-time-3",
            status=IngestionRunStatus.COMPLETED_WITH_WARNINGS,
            started_at=start,
            completed_at=None,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            warnings=[ManifestIssue(code="w", message="warn")],
        )


def test_status_and_issue_consistency_rules() -> None:
    start = datetime.now(UTC)

    # Failed status without failures rejected
    with pytest.raises(ValidationError, match="FAILED status requires at least one failure"):
        IngestionManifest(
            run_id="run-fail-empty",
            status=IngestionRunStatus.FAILED,
            started_at=start,
            completed_at=start,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            failures=[],
        )

    # Completed with warnings without warnings rejected
    with pytest.raises(ValidationError, match="requires at least one warning"):
        IngestionManifest(
            run_id="run-warn-empty",
            status=IngestionRunStatus.COMPLETED_WITH_WARNINGS,
            started_at=start,
            completed_at=start,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            warnings=[],
        )

    # Completed status with failures rejected
    with pytest.raises(ValidationError, match="COMPLETED status cannot contain failures"):
        IngestionManifest(
            run_id="run-comp-fail",
            status=IngestionRunStatus.COMPLETED,
            started_at=start,
            completed_at=start,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            failures=[ManifestIssue(code="f", message="fail")],
        )


def test_count_mismatch_rules() -> None:
    start = datetime.now(UTC)
    s1 = _sample_source(doc_id="d1", chunks=2)
    s2 = _sample_source(doc_id="d2", chunks=3)

    # Document count mismatch
    with pytest.raises(ValidationError, match="document_count must equal"):
        IngestionManifest(
            run_id="run-count-1",
            status=IngestionRunStatus.COMPLETED,
            started_at=start,
            completed_at=start,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            sources=[s1, s2],
            document_count=5,  # expected 2
            chunk_count=5,
        )

    # Chunk count mismatch
    with pytest.raises(ValidationError, match="chunk_count must equal"):
        IngestionManifest(
            run_id="run-count-2",
            status=IngestionRunStatus.COMPLETED,
            started_at=start,
            completed_at=start,
            loader_name="l",
            loader_version="1",
            chunker=ChunkerConfigSnapshot(),
            sources=[s1, s2],
            document_count=2,
            chunk_count=10,  # expected 5
        )


def test_chunker_snapshot_validation() -> None:
    # Target > max
    with pytest.raises(ValidationError):
        ChunkerConfigSnapshot(target_words=550, max_words=500)

    # Overlap >= target
    with pytest.raises(ValidationError):
        ChunkerConfigSnapshot(target_words=350, overlap_words=350)

    # Target out of range (< 350)
    with pytest.raises(ValidationError):
        ChunkerConfigSnapshot(target_words=200)

    # Overlap out of range (< 50)
    with pytest.raises(ValidationError):
        ChunkerConfigSnapshot(overlap_words=30)

    # Empty names
    with pytest.raises(ValidationError):
        ChunkerConfigSnapshot(chunker_name="")


def test_indexing_snapshot_validation() -> None:
    with pytest.raises(ValidationError):
        IndexingConfigSnapshot(embedding_model="", embedding_dimension=384, qdrant_collection="col")

    with pytest.raises(ValidationError):
        IndexingConfigSnapshot(
            embedding_model="model", embedding_dimension=0, qdrant_collection="col"
        )


def test_deterministic_serialization() -> None:
    start = datetime(2026, 9, 4, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 4, 1, 0, 2, tzinfo=UTC)
    s = _sample_source()
    manifest1 = IngestionManifest(
        run_id="run-determ-001",
        status=IngestionRunStatus.COMPLETED,
        started_at=start,
        completed_at=end,
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        sources=[s],
        document_count=1,
        chunk_count=3,
        metadata={"b": "beta", "a": "alpha"},
    )
    manifest2 = IngestionManifest(
        run_id="run-determ-001",
        status=IngestionRunStatus.COMPLETED,
        started_at=start,
        completed_at=end,
        loader_name="local-text-markdown",
        loader_version="1.0.0",
        chunker=ChunkerConfigSnapshot(),
        sources=[s],
        document_count=1,
        chunk_count=3,
        metadata={"a": "alpha", "b": "beta"},
    )

    bytes1 = serialize_manifest(manifest1).encode("utf-8")
    bytes2 = serialize_manifest(manifest2).encode("utf-8")

    assert bytes1 == bytes2
    text = bytes1.decode("utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert not bytes1.startswith(b"\xef\xbb\xbf")  # No BOM

    # Sorted keys check
    data = json.loads(text)
    keys = list(data.keys())
    assert keys == sorted(keys)

    # ISO 8601 formatting check
    assert "2026-09-04T01:00:00Z" in text or "2026-09-04T01:00:00+00:00" in text

from pathlib import Path

import pytest

from evidenceops.domain.errors import ArtifactConflictError, ArtifactValidationError
from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact


def artifact() -> ProcessedDocumentArtifact:
    document = DocumentRecord(
        document_id="doc-artifact",
        source_uri="file://data/raw/a.txt",
        title="A",
        source_type="text",
        content_sha256="a" * 64,
        text="alpha beta",
    )
    chunk = ChunkRecord(
        chunk_id="chunk-1",
        document_id="doc-artifact",
        text="alpha beta",
        title="A",
        ordinal=0,
        start_char=0,
        end_char=10,
        token_estimate=2,
    )
    return ProcessedDocumentArtifact(document=document, chunks=(chunk,))


def test_roundtrip_and_identical_write_is_unchanged(tmp_path: Path) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    first = store.write(artifact())
    original = first.path.read_bytes()
    second = store.write(artifact())
    assert first.disposition == "created"
    assert second.disposition == "unchanged"
    assert second.path.read_bytes() == original
    assert store.read("doc-artifact") == artifact()


def test_conflict_and_invalid_document_identifier_are_rejected(tmp_path: Path) -> None:
    store = JsonProcessedDocumentStore(tmp_path)
    store.write(artifact())
    changed = artifact().model_copy(update={"chunks": ()})
    with pytest.raises(ArtifactConflictError):
        store.write(changed)
    with pytest.raises(ArtifactValidationError):
        store.read("../unsafe")

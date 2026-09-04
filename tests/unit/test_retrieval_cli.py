import json
from pathlib import Path

import pytest

from evidenceops.cli import retrieval as retrieval_cli
from evidenceops.cli.retrieval import index_main, search_main
from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.contracts import RetrievalResult


def make_test_artifact(root: Path) -> None:
    store = JsonProcessedDocumentStore(root)
    chunk1 = ChunkRecord(
        chunk_id="chunk-cli-1",
        document_id="doc-cli-1",
        text="CLI indexing and searching in EvidenceOps.",
        title="CLI Guide",
        ordinal=0,
        start_char=0,
        end_char=42,
        token_estimate=6,
        metadata={"source_type": "markdown"},
    )
    doc1 = DocumentRecord(
        document_id="doc-cli-1",
        source_uri="docs/cli.md",
        title="CLI Guide",
        source_type="markdown",
        content_sha256="e" * 64,
        text="CLI indexing and searching in EvidenceOps.",
    )
    store.write(ProcessedDocumentArtifact(document=doc1, chunks=(chunk1,)))


def test_index_and_search_cli_sparse_workflow(tmp_path, capsys) -> None:
    processed_root = tmp_path / "processed"
    bm25_root = tmp_path / "bm25"
    make_test_artifact(processed_root)

    # 1. Run index command (sparse)
    exit_code = index_main(
        [
            "--processed-root",
            str(processed_root),
            "--bm25-root",
            str(bm25_root),
            "--index-id",
            "cli-test-index",
            "--build-sparse",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    index_out = json.loads(captured.out)
    assert index_out["status"] == "completed"
    assert index_out["sparse"]["index_id"] == "cli-test-index"
    assert (bm25_root / "cli-test-index.json").exists()

    # 2. Run search command (sparse)
    exit_code = search_main(
        [
            "--query",
            "CLI indexing",
            "--method",
            "sparse",
            "--processed-root",
            str(processed_root),
            "--bm25-root",
            str(bm25_root),
            "--index-id",
            "cli-test-index",
            "--top-k",
            "1",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    results = json.loads(captured.out)
    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk-cli-1"
    assert results[0]["retrieval_method"] == "sparse"
    assert results[0]["rank"] == 1


def test_search_cli_fails_on_empty_query(tmp_path, capsys) -> None:
    processed_root = tmp_path / "processed"
    make_test_artifact(processed_root)

    exit_code = search_main(
        [
            "--query",
            "   ",
            "--method",
            "sparse",
            "--processed-root",
            str(processed_root),
        ]
    )
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_cli_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as exc_info:
        index_main(["--help"])
    assert exc_info.value.code == 0

    with pytest.raises(SystemExit) as exc_info:
        search_main(["--help"])
    assert exc_info.value.code == 0


def test_sparse_cli_uses_shared_documentation_service(tmp_path, capsys, monkeypatch) -> None:
    processed_root = tmp_path / "processed"
    make_test_artifact(processed_root)
    artifact = JsonProcessedDocumentStore(processed_root).read("doc-cli-1")
    chunk = artifact.chunks[0]

    class FakeDocumentationService:
        def __init__(self) -> None:
            self.requests = []

        def search_results(self, request):
            self.requests.append(request)
            return (
                RetrievalResult(
                    chunk=chunk,
                    retrieval_method="sparse",
                    rank=1,
                    score=3.0,
                    sparse_rank=1,
                    sparse_score=3.0,
                    metadata={"source_type": "markdown"},
                ),
            )

    fake_service = FakeDocumentationService()
    monkeypatch.setattr(
        retrieval_cli,
        "build_documentation_service",
        lambda _settings: fake_service,
        raising=False,
    )

    exit_code = search_main(
        [
            "--query",
            "CLI indexing",
            "--method",
            "sparse",
            "--processed-root",
            str(processed_root),
            "--bm25-root",
            str(tmp_path / "bm25"),
            "--top-k",
            "1",
        ]
    )

    assert exit_code == 0
    assert fake_service.requests[0].query == "CLI indexing"
    assert json.loads(capsys.readouterr().out)[0]["score"] == 3.0

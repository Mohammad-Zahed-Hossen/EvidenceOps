"""End-to-end integration tests for local multi-format corpus ingestion."""

from pathlib import Path

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.ingestion.manifest import JsonManifestStore
from evidenceops.ingestion.pipeline import IngestionRequest, LocalIngestionPipeline


def test_end_to_end_corpus_ingestion_and_idempotency(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    processed_root = tmp_path / "processed"
    manifest_root = tmp_path / "manifests"

    raw_root.mkdir()
    processed_root.mkdir()
    manifest_root.mkdir()

    # 1. Prepare multi-format corpus
    # Markdown with nested headings and fenced code
    md_file = raw_root / "guide.md"
    md_file.write_text(
        "# EvidenceOps Guide\n\n"
        "Introduction to cost-aware retrieval.\n\n"
        "## Architecture\n\n"
        "Here is the architecture overview.\n\n"
        "```python\n"
        "def run_retrieval(query: str) -> None:\n"
        "    print(query)\n"
        "```\n",
        encoding="utf-8",
    )

    # Plain text document with multiple paragraphs
    txt_file = raw_root / "notes.txt"
    txt_file.write_text(
        "First paragraph with basic notes.\n\n"
        "Second paragraph with additional engineering requirements.\n\n"
        "Third paragraph describing the bounded controller limits.\n",
        encoding="utf-8",
    )

    # HTML document with headings, lists, pre/code
    html_file = raw_root / "api_doc.html"
    html_file.write_text(
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><title>API Spec</title><style>body { color: red; }</style></head>\n"
        "<body>\n"
        "<h1>API Specification</h1>\n"
        "<p>This document details the local endpoints.</p>\n"
        "<ul><li>GET /health</li><li>POST /query</li></ul>\n"
        "<pre><code class=\"language-python\">print('API ready')</code></pre>\n"
        "</body>\n"
        "</html>\n",
        encoding="utf-8",
    )

    pipeline = LocalIngestionPipeline(
        raw_root=raw_root,
        processed_root=processed_root,
        manifest_root=manifest_root,
    )

    # 2. First ingestion run
    req1 = IngestionRequest(
        run_id="run-initial-001",
        source_paths=(md_file, txt_file, html_file),
    )
    res1 = pipeline.ingest(req1)

    assert res1.manifest.status == IngestionRunStatus.COMPLETED
    assert len(res1.document_ids) == 3
    assert res1.created_artifact_count == 3
    assert res1.unchanged_artifact_count == 0
    assert res1.failed_source_count == 0

    # Verify manifest file on disk
    manifest_store = JsonManifestStore(manifest_root)
    saved_manifest = manifest_store.read("run-initial-001")
    assert saved_manifest.status == IngestionRunStatus.COMPLETED
    assert saved_manifest.document_count == 3

    # Verify processed artifacts on disk
    artifact_store = JsonProcessedDocumentStore(processed_root)
    for doc_id in res1.document_ids:
        artifact = artifact_store.read(doc_id)
        assert artifact.document.document_id == doc_id
        assert len(artifact.chunks) > 0
        assert all(c.document_id == doc_id for c in artifact.chunks)

    # 3. Second run with unchanged files and different run ID
    req2 = IngestionRequest(
        run_id="run-rerun-002",
        source_paths=(html_file, md_file, txt_file),  # different order
    )
    res2 = pipeline.ingest(req2)

    assert res2.manifest.status == IngestionRunStatus.COMPLETED
    # Deterministic IDs and canonical sorted order
    assert res2.document_ids == res1.document_ids
    assert res2.chunk_ids == res1.chunk_ids
    # Idempotency: unchanged artifacts skipped, 0 created
    assert res2.created_artifact_count == 0
    assert res2.unchanged_artifact_count == 3

    # 4. Modify one source file and ingest
    txt_file.write_text("Modified plain text content with updated rules.", encoding="utf-8")
    req3 = IngestionRequest(
        run_id="run-modified-003",
        source_paths=(md_file, txt_file, html_file),
    )
    res3 = pipeline.ingest(req3)

    assert res3.manifest.status == IngestionRunStatus.COMPLETED
    assert res3.created_artifact_count == 1  # only modified file produced a new artifact
    assert res3.unchanged_artifact_count == 2  # md and html were unchanged

    # 5. Partial failure test: add an empty file
    empty_file = raw_root / "empty.md"
    empty_file.write_text("   \n\n   ", encoding="utf-8")  # only whitespace

    req4 = IngestionRequest(
        run_id="run-failure-004",
        source_paths=(md_file, empty_file),
    )
    res4 = pipeline.ingest(req4)

    assert res4.manifest.status == IngestionRunStatus.FAILED
    assert res4.failed_source_count == 1
    assert len(res4.manifest.failures) == 1
    assert "source file must not be empty" in res4.manifest.failures[0].message

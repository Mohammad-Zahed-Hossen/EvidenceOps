from pathlib import Path

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.ingestion.pipeline import IngestionRequest, LocalIngestionPipeline


def test_pipeline_ingests_sorted_sources_and_is_idempotent(tmp_path: Path) -> None:
    raw, processed, manifests = tmp_path / "raw", tmp_path / "processed", tmp_path / "manifests"
    raw.mkdir()
    (raw / "b.txt").write_text("plain text", encoding="utf-8")
    (raw / "a.md").write_text("# Heading\n\nmarkdown text", encoding="utf-8")
    pipeline = LocalIngestionPipeline(raw, processed, manifests)
    first = pipeline.ingest(IngestionRequest("run-one", (raw / "b.txt", raw / "a.md")))
    second = pipeline.ingest(IngestionRequest("run-two", (raw / "a.md", raw / "b.txt")))
    assert first.manifest.status == IngestionRunStatus.COMPLETED
    assert first.created_artifact_count == 2
    assert second.unchanged_artifact_count == 2
    assert first.document_ids == second.document_ids
    assert first.manifest.sources[0].source_uri.endswith("a.md")

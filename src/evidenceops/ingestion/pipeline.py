"""Sequential local ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.domain.errors import IngestionError
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.ingestion.chunker import MarkdownChunker
from evidenceops.ingestion.loaders import LocalTextMarkdownLoader
from evidenceops.ingestion.manifest import (
    ChunkerConfigSnapshot,
    IngestionManifest,
    JsonManifestStore,
    ManifestIssue,
    ManifestSource,
    validate_run_id,
)
from evidenceops.ingestion.text_chunker import PlainTextChunker


@dataclass(frozen=True, slots=True)
class IngestionRequest:
    run_id: str
    source_paths: tuple[Path, ...]
    overwrite_artifacts: bool = False


@dataclass(frozen=True, slots=True)
class IngestionResult:
    run_id: str
    manifest: IngestionManifest
    manifest_path: Path
    artifact_paths: tuple[Path, ...]
    document_ids: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    created_artifact_count: int
    unchanged_artifact_count: int
    failed_source_count: int


class LocalIngestionPipeline:
    def __init__(self, raw_root: Path, processed_root: Path, manifest_root: Path) -> None:
        self.loader = LocalTextMarkdownLoader(raw_root)
        self.artifacts = JsonProcessedDocumentStore(processed_root)
        self.manifests = JsonManifestStore(manifest_root)
        self.markdown_chunker = MarkdownChunker()
        self.text_chunker = PlainTextChunker()

    def ingest(self, request: IngestionRequest) -> IngestionResult:
        try:
            validate_run_id(request.run_id)
        except ValueError as exc:
            raise IngestionError("invalid ingestion request run ID") from exc
        if not request.source_paths:
            raise IngestionError("ingestion request must include at least one source")
        paths = tuple(sorted(request.source_paths, key=lambda path: path.as_posix().lower()))
        if len({path.resolve() for path in paths}) != len(paths):
            raise IngestionError("ingestion request contains duplicate source paths")
        started = datetime.now(UTC)
        sources: list[ManifestSource] = []
        failures: list[ManifestIssue] = []
        artifact_paths: list[Path] = []
        document_ids: list[str] = []
        chunk_ids: list[str] = []
        created = unchanged = 0
        for path in paths:
            tick = perf_counter()
            try:
                document = self.loader.load(path)
                chunks = (
                    self.text_chunker.chunk(document)
                    if document.source_type == "text"
                    else self.markdown_chunker.chunk(document)
                )
                if document.document_id in document_ids or any(
                    chunk.chunk_id in chunk_ids for chunk in chunks
                ):
                    raise IngestionError("duplicate document or chunk identity in ingestion run")
                result = self.artifacts.write(
                    ProcessedDocumentArtifact(document=document, chunks=tuple(chunks)),
                    overwrite=request.overwrite_artifacts,
                )
                artifact_paths.append(result.path)
                document_ids.append(document.document_id)
                chunk_ids.extend(chunk.chunk_id for chunk in chunks)
                created += result.disposition in {"created", "overwritten"}
                unchanged += result.disposition == "unchanged"
                sources.append(
                    ManifestSource(
                        source_uri=document.source_uri,
                        document_id=document.document_id,
                        source_type=document.source_type,
                        content_sha256=document.content_sha256,
                        byte_size=int(document.metadata["byte_size"]),
                        chunk_count=len(chunks),
                    )
                )
            except IngestionError as exc:
                failures.append(
                    ManifestIssue(
                        code=exc.code,
                        message=exc.message,
                        source_uri=str(path),
                        recoverable=False,
                    )
                )
            _ = tick
        status = IngestionRunStatus.FAILED if failures else IngestionRunStatus.COMPLETED
        manifest = IngestionManifest(
            run_id=request.run_id,
            status=status,
            started_at=started,
            completed_at=datetime.now(UTC),
            loader_name="local-file",
            loader_version="1.0",
            chunker=ChunkerConfigSnapshot(),
            sources=sources,
            document_count=len(sources),
            chunk_count=len(chunk_ids),
            failures=failures,
        )
        manifest_path = self.manifests.write(manifest)
        return IngestionResult(
            request.run_id,
            manifest,
            manifest_path,
            tuple(artifact_paths),
            tuple(document_ids),
            tuple(chunk_ids),
            created,
            unchanged,
            len(failures),
        )

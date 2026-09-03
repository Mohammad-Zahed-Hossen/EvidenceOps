"""Local ingestion boundaries for EvidenceOps."""

from evidenceops.ingestion.artifacts import (
    ArtifactWriteResult,
    JsonProcessedDocumentStore,
    ProcessedDocumentArtifact,
)
from evidenceops.ingestion.chunker import DocumentChunker, MarkdownChunker
from evidenceops.ingestion.loaders import LocalTextMarkdownLoader, SourceLoader
from evidenceops.ingestion.manifest import (
    ChunkerConfigSnapshot,
    IndexingConfigSnapshot,
    IngestionManifest,
    JsonManifestStore,
    ManifestIssue,
    ManifestSource,
    ManifestStore,
    serialize_manifest,
    validate_run_id,
)
from evidenceops.ingestion.normalizer import normalize_html
from evidenceops.ingestion.pipeline import (
    IngestionRequest,
    IngestionResult,
    LocalIngestionPipeline,
)
from evidenceops.ingestion.text_chunker import PlainTextChunker

__all__ = [
    "ArtifactWriteResult",
    "ChunkerConfigSnapshot",
    "DocumentChunker",
    "IndexingConfigSnapshot",
    "IngestionManifest",
    "IngestionRequest",
    "IngestionResult",
    "JsonManifestStore",
    "JsonProcessedDocumentStore",
    "LocalIngestionPipeline",
    "LocalTextMarkdownLoader",
    "ManifestIssue",
    "ManifestSource",
    "ManifestStore",
    "MarkdownChunker",
    "PlainTextChunker",
    "ProcessedDocumentArtifact",
    "SourceLoader",
    "normalize_html",
    "serialize_manifest",
    "validate_run_id",
]

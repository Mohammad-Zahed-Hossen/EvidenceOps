"""Small, framework-independent error hierarchy."""

from collections.abc import Mapping


class EvidenceOpsError(Exception):
    """Base exception with a stable code and non-sensitive string form."""

    default_code = "evidenceops_error"

    def __init__(
        self, message: str, *, code: str | None = None, context: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.context = dict(context or {})

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigurationError(EvidenceOpsError):
    default_code = "configuration_error"


class DomainValidationError(EvidenceOpsError):
    default_code = "domain_validation_error"


class DependencyUnavailableError(EvidenceOpsError):
    default_code = "dependency_unavailable"


class RetrievalError(EvidenceOpsError):
    default_code = "retrieval_error"


class GenerationError(EvidenceOpsError):
    default_code = "generation_error"


class AbstentionError(EvidenceOpsError):
    default_code = "abstention_error"


class IngestionError(EvidenceOpsError):
    default_code = "ingestion_error"


class UnsupportedSourceError(IngestionError):
    default_code = "unsupported_source"


class SourceAccessError(IngestionError):
    default_code = "source_access_error"


class SourceEncodingError(IngestionError):
    default_code = "source_encoding_error"


class ChunkingError(IngestionError):
    default_code = "chunking_error"


class ArtifactError(IngestionError):
    default_code = "artifact_error"


class ArtifactConflictError(ArtifactError):
    default_code = "artifact_conflict"


class ArtifactNotFoundError(ArtifactError):
    default_code = "artifact_not_found"


class ArtifactValidationError(ArtifactError):
    default_code = "artifact_validation_error"


class ManifestError(IngestionError):
    default_code = "manifest_error"


class ManifestNotFoundError(ManifestError):
    default_code = "manifest_not_found"


class ManifestConflictError(ManifestError):
    default_code = "manifest_conflict"


class ManifestSerializationError(ManifestError):
    default_code = "manifest_serialization_error"


class ManifestValidationError(ManifestError):
    default_code = "manifest_validation_error"


class RetrievalQueryError(RetrievalError):
    default_code = "retrieval_query_error"


class SparseIndexError(RetrievalError):
    default_code = "sparse_index_error"


class EmbeddingError(RetrievalError):
    default_code = "embedding_error"


class VectorStoreError(RetrievalError):
    default_code = "vector_store_error"


class RerankingError(RetrievalError):
    default_code = "reranking_error"

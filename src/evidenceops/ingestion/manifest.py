"""Ingestion manifest models, deterministic JSON serialization, and atomic local persistence."""

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.domain.errors import (
    ManifestConflictError,
    ManifestNotFoundError,
    ManifestValidationError,
)

RUN_ID_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HEX_64_REGEX = re.compile(r"^[a-f0-9]{64}$")


def validate_run_id(run_id: str) -> str:
    """Validate that run_id is non-empty, safe for filenames, and lacks path traversal."""
    if not isinstance(run_id, str):
        raise ValueError("run_id must be a string")
    if not run_id or not run_id.strip():
        raise ValueError("run_id cannot be empty or whitespace only")
    if run_id != run_id.strip():
        raise ValueError("run_id cannot contain leading or trailing whitespace")
    if "\x00" in run_id:
        raise ValueError("run_id cannot contain null characters")
    if "/" in run_id or "\\" in run_id or ":" in run_id:
        raise ValueError("run_id cannot contain path separators or drive prefixes")
    if run_id in {".", ".."}:
        raise ValueError("run_id cannot be '.' or '..'")
    if not RUN_ID_REGEX.match(run_id):
        raise ValueError(
            f"run_id '{run_id}' does not match allowed pattern (must begin with alphanumeric)"
        )
    return run_id


class ManifestIssue(BaseModel):
    """Represents a diagnostic warning or failure in an ingestion run."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    source_uri: str | None = None
    recoverable: bool = False

    @field_validator("code", "message")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return value


class ManifestSource(BaseModel):
    """Represents a processed source document included in an ingestion run."""

    model_config = ConfigDict(extra="forbid")

    source_uri: str
    document_id: str
    source_type: str
    content_sha256: str
    byte_size: int = Field(ge=0)
    chunk_count: int = Field(ge=0)

    @field_validator("source_uri", "document_id", "source_type")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return value

    @field_validator("content_sha256")
    @classmethod
    def check_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not HEX_64_REGEX.match(normalized):
            raise ValueError("content_sha256 must be a 64-character hexadecimal string")
        return normalized


class ChunkerConfigSnapshot(BaseModel):
    """Immutable snapshot of the chunker configuration used for a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunker_name: str = "markdown-structure-aware"
    chunker_version: str = "1"
    target_words: int = Field(default=500, ge=350, le=600)
    max_words: int = Field(default=600, ge=350, le=600)
    overlap_words: int = Field(default=60, ge=50, le=80)
    word_count_strategy: str = "non_whitespace_tokens"

    @field_validator("chunker_name", "chunker_version", "word_count_strategy")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return value

    @model_validator(mode="after")
    def validate_word_bounds(self) -> "ChunkerConfigSnapshot":
        if self.target_words > self.max_words:
            raise ValueError("target_words cannot exceed max_words")
        if self.overlap_words >= self.target_words:
            raise ValueError("overlap_words must be strictly less than target_words")
        return self


class IndexingConfigSnapshot(BaseModel):
    """Optional snapshot of indexing configuration for future vector storage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    embedding_model: str
    embedding_dimension: int = Field(gt=0)
    qdrant_collection: str

    @field_validator("embedding_model", "qdrant_collection")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return value


class IngestionManifest(BaseModel):
    """Complete, validated manifest representing an ingestion execution run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    run_id: str
    status: IngestionRunStatus
    started_at: datetime
    completed_at: datetime | None = None

    loader_name: str
    loader_version: str
    chunker: ChunkerConfigSnapshot

    sources: list[ManifestSource] = Field(default_factory=list)
    document_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)

    warnings: list[ManifestIssue] = Field(default_factory=list)
    failures: list[ManifestIssue] = Field(default_factory=list)

    indexing: IndexingConfigSnapshot | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def validate_run_id_field(cls, value: str) -> str:
        return validate_run_id(value)

    @field_validator("schema_version", "loader_name", "loader_version")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return value

    @model_validator(mode="after")
    def validate_manifest_consistency(self) -> "IngestionManifest":
        # Timestamp consistency
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be earlier than started_at")

        # Status vs completed_at
        if self.status in {
            IngestionRunStatus.COMPLETED,
            IngestionRunStatus.COMPLETED_WITH_WARNINGS,
        }:
            if self.completed_at is None:
                raise ValueError(f"{self.status} completed status requires completed_at timestamp")

        # Status vs failures/warnings
        if self.status == IngestionRunStatus.FAILED:
            if not self.failures:
                raise ValueError("FAILED status requires at least one failure")
        elif self.status == IngestionRunStatus.COMPLETED_WITH_WARNINGS:
            if not self.warnings:
                raise ValueError("COMPLETED_WITH_WARNINGS status requires at least one warning")
            if self.failures:
                raise ValueError(
                    "COMPLETED_WITH_WARNINGS status cannot contain unrecoverable failures"
                )
        elif self.status == IngestionRunStatus.COMPLETED:
            if self.failures:
                raise ValueError("COMPLETED status cannot contain failures")

        # Count consistency
        actual_docs = len(self.sources)
        if self.document_count != actual_docs:
            raise ValueError(
                f"document_count must equal number of sources ({actual_docs}), "
                f"got {self.document_count}"
            )

        actual_chunks = sum(s.chunk_count for s in self.sources)
        if self.chunk_count != actual_chunks:
            raise ValueError(
                f"chunk_count must equal sum of source chunk counts ({actual_chunks}), "
                f"got {self.chunk_count}"
            )

        return self


def serialize_manifest(manifest: IngestionManifest) -> str:
    """Serialize an IngestionManifest to deterministic, UTF-8 JSON text."""
    payload = manifest.model_dump(mode="json")
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


class ManifestStore(Protocol):
    """Protocol for reading and writing ingestion manifests."""

    def write(
        self,
        manifest: IngestionManifest,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write manifest atomically. Raise ManifestConflictError if exists and not overwrite."""
        ...

    def read(self, run_id: str) -> IngestionManifest:
        """Read and validate manifest for run_id."""
        ...


class JsonManifestStore:
    """Atomic, local filesystem manifest store using deterministic JSON formatting."""

    def __init__(self, manifest_root: Path) -> None:
        self.manifest_root = manifest_root.resolve()

    def _resolve_run_path(self, run_id: str) -> Path:
        """Validate run_id and resolve the destination path ensuring no directory traversal."""
        try:
            valid_id = validate_run_id(run_id)
        except ValueError as exc:
            raise ManifestValidationError(
                f"Invalid run_id '{run_id}': {exc}",
                context={"run_id": run_id},
            ) from exc

        path = (self.manifest_root / f"{valid_id}.json").resolve()
        if path.parent != self.manifest_root:
            raise ManifestValidationError(
                f"Resolved path for '{run_id}' escaped manifest root",
                context={"run_id": run_id, "path": str(path)},
            )
        return path

    def write(
        self,
        manifest: IngestionManifest,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Atomically persist manifest to disk.

        Creates temporary file in the same directory, flushes, syncs to disk,
        and atomically replaces the target path.
        """
        final_path = self._resolve_run_path(manifest.run_id)

        # Conflict check prior to disk write
        if final_path.exists() and not overwrite:
            raise ManifestConflictError(
                f"Manifest for run '{manifest.run_id}' already exists at {final_path}",
                context={"run_id": manifest.run_id, "path": str(final_path)},
            )

        json_text = serialize_manifest(manifest)
        json_bytes = json_text.encode("utf-8")

        self.manifest_root.mkdir(parents=True, exist_ok=True)

        temp_file_path: Path | None = None
        try:
            fd, temp_name = tempfile.mkstemp(
                dir=self.manifest_root,
                prefix=f".tmp_{manifest.run_id}_",
                suffix=".tmp",
            )
            temp_file_path = Path(temp_name)
            with os.fdopen(fd, "wb") as f:
                f.write(json_bytes)
                f.flush()
                os.fsync(f.fileno())

            # Re-verify conflict check just before atomic replace if overwrite is False
            if final_path.exists() and not overwrite:
                raise ManifestConflictError(
                    f"Manifest for run '{manifest.run_id}' already exists at {final_path}",
                    context={"run_id": manifest.run_id, "path": str(final_path)},
                )

            os.replace(temp_file_path, final_path)
            temp_file_path = None
            return final_path
        finally:
            if temp_file_path is not None and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except OSError:
                    pass

    def read(self, run_id: str) -> IngestionManifest:
        """Read and validate an existing manifest by run ID."""
        final_path = self._resolve_run_path(run_id)

        if not final_path.exists() or not final_path.is_file():
            raise ManifestNotFoundError(
                f"Manifest for run '{run_id}' not found at {final_path}",
                context={"run_id": run_id, "path": str(final_path)},
            )

        try:
            text = final_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise ManifestValidationError(
                f"Failed to read manifest file at {final_path}: {exc}",
                context={"run_id": run_id, "path": str(final_path)},
            ) from exc

        try:
            data: Any = json.loads(text)
        except Exception as exc:
            raise ManifestValidationError(
                f"Invalid JSON in manifest file at {final_path}: {exc}",
                context={"run_id": run_id, "path": str(final_path)},
            ) from exc

        if not isinstance(data, dict):
            raise ManifestValidationError(
                f"Manifest content must be a JSON object, got {type(data).__name__}",
                context={"run_id": run_id, "path": str(final_path)},
            )

        try:
            return IngestionManifest.model_validate(data)
        except Exception as exc:
            raise ManifestValidationError(
                f"Schema validation failed for manifest at {final_path}: {exc}",
                context={"run_id": run_id, "path": str(final_path)},
            ) from exc

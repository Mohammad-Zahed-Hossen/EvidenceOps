"""Portable deterministic processed-document artifact persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from evidenceops.domain.errors import (
    ArtifactConflictError,
    ArtifactNotFoundError,
    ArtifactValidationError,
)
from evidenceops.domain.models import ChunkRecord, DocumentRecord

SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ProcessedDocumentArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    document: DocumentRecord
    chunks: tuple[ChunkRecord, ...]

    @model_validator(mode="after")
    def validate_chunks(self) -> ProcessedDocumentArtifact:
        ordinals = [chunk.ordinal for chunk in self.chunks]
        identifiers = [chunk.chunk_id for chunk in self.chunks]
        if any(chunk.document_id != self.document.document_id for chunk in self.chunks):
            raise ValueError("every chunk must belong to the artifact document")
        if len(ordinals) != len(set(ordinals)) or ordinals != sorted(ordinals):
            raise ValueError("chunk ordinals must be unique and ordered")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("chunk IDs must be unique")
        if any(chunk.end_char > len(self.document.text) for chunk in self.chunks):
            raise ValueError("chunk offsets must fall within document text")
        return self


@dataclass(frozen=True, slots=True)
class ArtifactWriteResult:
    path: Path
    disposition: Literal["created", "unchanged", "overwritten"]


def serialize_artifact(artifact: ProcessedDocumentArtifact) -> bytes:
    dumped = json.dumps(
        artifact.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (dumped + "\n").encode("utf-8")


class JsonProcessedDocumentStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, document_id: str) -> Path:
        if not SAFE_ID.fullmatch(document_id) or document_id in {".", ".."}:
            raise ArtifactValidationError(
                "invalid document identifier", context={"document_id": document_id}
            )
        path = (self.root / f"{document_id}.json").resolve()
        if path.parent != self.root:
            raise ArtifactValidationError("artifact path escaped processed root")
        return path

    def write(
        self, artifact: ProcessedDocumentArtifact, *, overwrite: bool = False
    ) -> ArtifactWriteResult:
        try:
            validated = ProcessedDocumentArtifact.model_validate(artifact)
        except Exception as exc:
            raise ArtifactValidationError("artifact validation failed") from exc
        path = self._path(validated.document.document_id)
        payload = serialize_artifact(validated)
        if path.exists():
            if path.read_bytes() == payload:
                return ArtifactWriteResult(path, "unchanged")
            if not overwrite:
                raise ArtifactConflictError(
                    "processed artifact already exists",
                    context={"document_id": validated.document.document_id},
                )
        self.root.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            fd, name = tempfile.mkstemp(prefix=".tmp_", suffix=".tmp", dir=self.root)
            temporary = Path(name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
        return ArtifactWriteResult(
            path, "overwritten" if overwrite and path.exists() else "created"
        )

    def read(self, document_id: str) -> ProcessedDocumentArtifact:
        path = self._path(document_id)
        if not path.is_file():
            raise ArtifactNotFoundError(
                "processed artifact was not found", context={"document_id": document_id}
            )
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            return ProcessedDocumentArtifact.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ArtifactValidationError(
                "processed artifact is invalid", context={"document_id": document_id}
            ) from exc

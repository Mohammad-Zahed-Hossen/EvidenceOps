"""Deterministic, rebuildable BM25 snapshot persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from evidenceops.domain.errors import SparseIndexError

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SCHEMA_VERSION = "1.0"


class SparseIndexSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    index_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    tokenizer_version: str
    bm25_k1: float
    bm25_b: float
    chunk_ids: tuple[str, ...]
    document_ids: tuple[str, ...]
    tokenized_corpus: tuple[tuple[str, ...], ...]
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SparseIndexWriteResult:
    path: Path
    disposition: str


def fingerprint(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JsonSparseIndexStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, index_id: str) -> Path:
        if not _SAFE_ID.fullmatch(index_id):
            raise SparseIndexError(
                "invalid sparse index identifier", context={"index_id": index_id}
            )
        path = (self.root / f"{index_id}.json").resolve()
        if path.parent != self.root:
            raise SparseIndexError("sparse index path escaped index root")
        return path

    @staticmethod
    def _serialize(snapshot: SparseIndexSnapshot) -> bytes:
        payload = json.dumps(
            snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
        )
        return (payload + "\n").encode("utf-8")

    def write(self, snapshot: SparseIndexSnapshot) -> SparseIndexWriteResult:
        path = self._path(snapshot.index_id)
        payload = self._serialize(snapshot)
        if path.exists():
            if path.read_bytes() == payload:
                return SparseIndexWriteResult(path, "unchanged")
            raise SparseIndexError(
                "sparse index already exists", context={"index_id": snapshot.index_id}
            )
        self.root.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(prefix=".tmp_", suffix=".tmp", dir=self.root)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
        return SparseIndexWriteResult(path, "created")

    def load(self, index_id: str) -> SparseIndexSnapshot:
        path = self._path(index_id)
        if not path.exists():
            raise SparseIndexError(f"sparse index not found: {index_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            snapshot = SparseIndexSnapshot.model_validate(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SparseIndexError("sparse index snapshot is invalid") from exc
        if snapshot.schema_version != SCHEMA_VERSION:
            raise SparseIndexError("unsupported sparse index schema version")
        if not (
            len(snapshot.chunk_ids) == len(snapshot.document_ids) == len(snapshot.tokenized_corpus)
        ) or len(set(snapshot.chunk_ids)) != len(snapshot.chunk_ids):
            raise SparseIndexError("sparse index snapshot has inconsistent corpus data")
        return snapshot

"""Safe, deterministic single-file local text and Markdown loading."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from evidenceops.domain.errors import (
    IngestionError,
    SourceAccessError,
    SourceEncodingError,
    UnsupportedSourceError,
)
from evidenceops.domain.models import DocumentRecord


class SourceLoader(Protocol):
    """A framework-independent interface for loading exactly one local source."""

    def load(self, source_path: Path) -> DocumentRecord:
        """Load one validated source file into a document contract."""


class LocalTextMarkdownLoader:
    """Load one permitted UTF-8 text or Markdown file without filesystem discovery."""

    _source_types = {".md": "markdown", ".markdown": "markdown", ".txt": "text"}
    _heading_pattern = re.compile(r"^\s{0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")

    def __init__(self, allowed_root: Path, max_source_bytes: int = 10_000_000) -> None:
        if max_source_bytes < 1:
            raise ValueError("max_source_bytes must be positive")
        try:
            self._allowed_root = allowed_root.expanduser().resolve(strict=True)
        except OSError as exc:
            raise SourceAccessError("allowed root is not accessible") from exc
        if not self._allowed_root.is_dir():
            raise SourceAccessError("allowed root must be a directory")
        self._max_source_bytes = max_source_bytes

    def load(self, source_path: Path) -> DocumentRecord:
        """Read one permitted file and return its deterministic document record."""
        resolved_path = self._resolve_source(source_path)
        extension = resolved_path.suffix.lower()
        source_type = self._source_types.get(extension)
        if source_type is None:
            raise UnsupportedSourceError(
                "source extension is not supported", context={"extension": extension}
            )

        try:
            stat = resolved_path.stat()
        except OSError as exc:
            raise SourceAccessError("source file is not accessible") from exc
        if stat.st_size > self._max_source_bytes:
            raise SourceAccessError("source file exceeds the configured size limit")

        try:
            text = resolved_path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SourceEncodingError("source file is not valid UTF-8") from exc
        except OSError as exc:
            raise SourceAccessError("source file could not be read") from exc
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise IngestionError("source file must not be empty")

        relative_path = resolved_path.relative_to(self._allowed_root).as_posix()
        source_uri = f"file://data/raw/{relative_path}"
        content_sha256 = sha256(text.encode("utf-8")).hexdigest()
        document_id = sha256(f"{source_uri}:{content_sha256}".encode()).hexdigest()
        return DocumentRecord(
            document_id=document_id,
            source_uri=source_uri,
            title=self._title_from(text, resolved_path.stem),
            source_type=source_type,
            content_sha256=content_sha256,
            text=text,
            source_updated_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            metadata={
                "extension": extension,
                "relative_path": relative_path,
                "byte_size": str(stat.st_size),
            },
        )

    def _resolve_source(self, source_path: Path) -> Path:
        try:
            resolved_path = source_path.expanduser().resolve(strict=True)
        except OSError as exc:
            raise SourceAccessError("source path does not exist or cannot be resolved") from exc
        try:
            resolved_path.relative_to(self._allowed_root)
        except ValueError as exc:
            raise SourceAccessError("source path is outside the allowed root") from exc
        if not resolved_path.is_file():
            raise SourceAccessError("source path must be a regular file")
        return resolved_path

    @classmethod
    def _title_from(cls, text: str, fallback: str) -> str:
        for line in text.split("\n"):
            match = cls._heading_pattern.match(line)
            if match and match.group(1).strip():
                return match.group(1).strip()
        return fallback

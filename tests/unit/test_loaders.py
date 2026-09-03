from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from evidenceops.domain.errors import (
    IngestionError,
    SourceAccessError,
    SourceEncodingError,
    UnsupportedSourceError,
)
from evidenceops.domain.models import DocumentRecord
from evidenceops.ingestion.loaders import LocalTextMarkdownLoader


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "raw"
    root.mkdir()
    return root


def write_file(root: Path, name: str, content: bytes) -> Path:
    path = root / name
    path.write_bytes(content)
    return path


@pytest.mark.parametrize(
    ("name", "content", "source_type", "title"),
    [
        ("guide.md", b"# Guide\r\n\r\nBody\rText", "markdown", "Guide"),
        ("guide.markdown", b"## Guide\nBody", "markdown", "Guide"),
        ("notes.txt", b"Plain text", "text", "notes"),
    ],
)
def test_loads_supported_files_with_normalized_text_and_metadata(
    source_root: Path, name: str, content: bytes, source_type: str, title: str
) -> None:
    source = write_file(source_root, name, content)
    record = LocalTextMarkdownLoader(source_root).load(source)
    normalized = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert isinstance(record, DocumentRecord)
    assert record.source_type == source_type
    assert record.title == title
    assert record.text == normalized
    assert record.source_uri == f"file://data/raw/{name}"
    assert record.content_sha256 == sha256(normalized.encode("utf-8")).hexdigest()
    assert record.metadata == {
        "extension": Path(name).suffix.lower(),
        "relative_path": name,
        "byte_size": str(len(content)),
    }


def test_accepts_utf8_bom_and_is_deterministic(source_root: Path) -> None:
    source = write_file(source_root, "bom.MD", b"\xef\xbb\xbf# Title\nText")
    loader = LocalTextMarkdownLoader(source_root)
    first, second = loader.load(source), loader.load(source)
    assert first.text == "# Title\nText"
    assert first.document_id == second.document_id
    assert first.source_uri == second.source_uri
    source.write_text("# Title\nChanged", encoding="utf-8")
    changed = loader.load(source)
    assert changed.content_sha256 != first.content_sha256
    assert changed.document_id != first.document_id


@pytest.mark.parametrize("name", ["missing.md", "folder", "report.pdf", "page.html", "image.png"])
def test_rejects_missing_directories_and_unsupported_sources(source_root: Path, name: str) -> None:
    if name == "folder":
        (source_root / name).mkdir()
    elif name not in {"missing.md", "folder"}:
        write_file(source_root, name, b"content")
    with pytest.raises((SourceAccessError, UnsupportedSourceError)):
        LocalTextMarkdownLoader(source_root).load(source_root / name)


@pytest.mark.parametrize("content", [b"", b" \t\r\n"])
def test_rejects_empty_documents(source_root: Path, content: bytes) -> None:
    with pytest.raises(IngestionError) as error:
        LocalTextMarkdownLoader(source_root).load(write_file(source_root, "empty.txt", content))
    assert error.value.code == "ingestion_error"
    if content:
        assert content.decode("utf-8", errors="ignore") not in str(error.value)


def test_rejects_malformed_utf8_and_oversized_files(source_root: Path) -> None:
    malformed = write_file(source_root, "bad.txt", b"\xff\xfe")
    with pytest.raises(SourceEncodingError) as error:
        LocalTextMarkdownLoader(source_root).load(malformed)
    assert error.value.code == "source_encoding_error"
    oversized = write_file(source_root, "large.txt", b"12345")
    with pytest.raises(SourceAccessError):
        LocalTextMarkdownLoader(source_root, max_source_bytes=4).load(oversized)


def test_rejects_paths_outside_allowed_root(source_root: Path, tmp_path: Path) -> None:
    outside = write_file(tmp_path, "outside.md", b"# Outside")
    loader = LocalTextMarkdownLoader(source_root)
    for source in (outside, source_root / ".." / "outside.md"):
        with pytest.raises(SourceAccessError) as error:
            loader.load(source)
        assert error.value.code == "source_access_error"
        assert "Outside" not in str(error.value)


def test_rejects_symlink_escaping_allowed_root_when_supported(
    source_root: Path, tmp_path: Path
) -> None:
    outside = write_file(tmp_path, "outside.md", b"# Outside")
    link = source_root / "linked.md"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(SourceAccessError):
        LocalTextMarkdownLoader(source_root).load(link)

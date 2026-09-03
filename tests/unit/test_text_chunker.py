from hashlib import sha256

import pytest

from evidenceops.domain.errors import ChunkingError
from evidenceops.domain.models import DocumentRecord
from evidenceops.ingestion.text_chunker import PlainTextChunker


def make_document(text: str, *, source_type: str = "text") -> DocumentRecord:
    return DocumentRecord(
        document_id="plain-doc",
        source_uri="file://data/raw/notes.txt",
        title="Notes",
        source_type=source_type,
        content_sha256="a" * 64,
        text=text,
    )


def test_chunks_paragraphs_deterministically_with_valid_offsets() -> None:
    text = "First paragraph has useful text.\n\nSecond paragraph has more useful text."
    chunker = PlainTextChunker(target_words=350, max_words=600, overlap_words=60)

    first = chunker.chunk(make_document(text))
    second = chunker.chunk(make_document(text))

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert [chunk.ordinal for chunk in first] == list(range(len(first)))
    assert "First paragraph" in first[0].text
    assert "Second paragraph" in first[-1].text
    for chunk in first:
        assert 0 <= chunk.start_char < chunk.end_char <= len(text)
        assert (
            chunk.chunk_id == sha256(f"plain-doc:{chunk.ordinal}:{chunk.text}".encode()).hexdigest()
        )
        assert chunk.metadata["heading_path"] == ""


def test_splits_oversized_paragraph_without_dropping_tokens() -> None:
    text = " ".join(f"word{index}" for index in range(713))
    chunks = PlainTextChunker(target_words=350, max_words=350, overlap_words=50).chunk(
        make_document(text)
    )

    combined_tokens = " ".join(chunk.text for chunk in chunks)
    for token in text.split():
        assert token in combined_tokens
    assert all(chunk.token_estimate <= 600 for chunk in chunks)
    assert all(chunk.start_char < chunk.end_char for chunk in chunks)


@pytest.mark.parametrize("source_type", ["markdown", "html"])
def test_rejects_incompatible_source_type(source_type: str) -> None:
    with pytest.raises(ChunkingError) as error:
        PlainTextChunker().chunk(make_document("content", source_type=source_type))
    assert error.value.code == "chunking_error"

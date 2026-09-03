from hashlib import sha256

import pytest

from evidenceops.domain.errors import ChunkingError
from evidenceops.domain.models import DocumentRecord
from evidenceops.ingestion.chunker import MarkdownChunker


def document(text: str, source_type: str = "markdown") -> DocumentRecord:
    return DocumentRecord(
        document_id="doc",
        source_uri="file://data/raw/doc.md",
        title="Doc",
        source_type=source_type,
        content_sha256="a" * 64,
        text=text,
    )


def test_chunker_preserves_heading_paths_offsets_and_deterministic_ids() -> None:
    text = "# Retrieval\n\n## Sparse\n\nBM25 finds exact terms.\n"
    chunks = MarkdownChunker().chunk(document(text))
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.metadata["heading_path"] == "Retrieval > Sparse"
    assert "BM25 finds exact terms." in text[chunk.start_char : chunk.end_char]
    assert chunk.chunk_id == sha256(f"doc:0:{chunk.text}".encode()).hexdigest()
    assert chunk.token_estimate == int(chunk.metadata["word_count"])


def test_chunker_ignores_heading_like_text_inside_fences_and_preserves_code() -> None:
    text = "# Real\n\n```python\n# not a heading\nprint('x')\n```\n\nAfter code.\n"
    chunk = MarkdownChunker().chunk(document(text))[0]
    assert "# not a heading" in chunk.text
    assert chunk.metadata["heading_path"] == "Real"
    assert chunk.metadata["contains_code"] == "true"
    assert chunk.metadata["code_languages"] == "python"


def test_chunker_keeps_oversized_fence_atomic_and_marks_unclosed_fence() -> None:
    code = " ".join("word" for _ in range(610))
    text = f"# Code\n\n```python\n{code}\n"
    chunks = MarkdownChunker().chunk(document(text))
    assert any(
        "```python" in chunk.text and chunk.metadata["oversized"] == "true" for chunk in chunks
    )
    assert any(chunk.metadata["unclosed_fence"] == "true" for chunk in chunks)


def test_chunker_creates_deterministic_prose_overlap() -> None:
    first = " ".join(f"first{i}" for i in range(400))
    second = " ".join(f"second{i}" for i in range(300))
    chunks = MarkdownChunker(target_words=500, max_words=600, overlap_words=60).chunk(
        document(f"# H\n\n{first}\n\n{second}")
    )
    assert len(chunks) >= 2
    assert chunks[0].metadata["overlap_words"] == "0"
    assert int(chunks[1].metadata["overlap_words"]) >= 50
    assert chunks[1].start_char < chunks[0].end_char


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_words": 349},
        {"max_words": 601},
        {"target_words": 550, "max_words": 500},
        {"overlap_words": 49},
    ],
)
def test_chunker_rejects_invalid_configuration(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        MarkdownChunker(**kwargs)


def test_chunker_rejects_non_markdown_and_empty_results() -> None:
    with pytest.raises(ChunkingError):
        MarkdownChunker().chunk(document("text", source_type="text"))

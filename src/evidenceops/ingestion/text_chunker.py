"""Deterministic paragraph-aware chunking for normalized plain text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from evidenceops.domain.errors import ChunkingError
from evidenceops.domain.models import ChunkRecord, DocumentRecord

TOKEN_PATTERN = re.compile(r"\S+")
PARAGRAPH_PATTERN = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)


@dataclass(frozen=True, slots=True)
class _Segment:
    start: int
    end: int
    words: int


class PlainTextChunker:
    """Chunk plain-text documents without transforming normalized source text."""

    def __init__(
        self,
        *,
        target_words: int = 500,
        max_words: int = 600,
        overlap_words: int = 60,
    ) -> None:
        if not 350 <= target_words <= 600:
            raise ValueError("target_words must be between 350 and 600")
        if not 350 <= max_words <= 600:
            raise ValueError("max_words must be between 350 and 600")
        if not 50 <= overlap_words <= 80:
            raise ValueError("overlap_words must be between 50 and 80")
        if target_words > max_words:
            raise ValueError("target_words cannot exceed max_words")
        if overlap_words >= target_words:
            raise ValueError("overlap_words must be strictly less than target_words")
        self.target_words = target_words
        self.max_words = max_words
        self.overlap_words = overlap_words

    def chunk(self, document: DocumentRecord) -> list[ChunkRecord]:
        """Return ordered chunks with half-open offsets into ``document.text``."""
        if document.source_type != "text":
            raise ChunkingError(
                "plain-text chunker requires a text document",
                context={"source_type": document.source_type},
            )
        segments = self._segments(document.text)
        if not segments:
            raise ChunkingError("plain-text document has no chunkable content")

        groups: list[list[_Segment]] = []
        current: list[_Segment] = []
        current_words = 0
        previous: list[_Segment] = []
        for segment in segments:
            if current and current_words + segment.words > self.max_words:
                groups.append(current)
                previous = current
                current = self._overlap(previous)
                current_words = sum(item.words for item in current)
            current.append(segment)
            current_words += segment.words
            if current_words >= self.target_words:
                groups.append(current)
                previous = current
                current = self._overlap(previous)
                current_words = sum(item.words for item in current)
        if current and (not groups or current != groups[-1]):
            groups.append(current)

        return [self._record(document, group, ordinal) for ordinal, group in enumerate(groups)]

    def _segments(self, text: str) -> list[_Segment]:
        segments: list[_Segment] = []
        for paragraph in PARAGRAPH_PATTERN.finditer(text):
            tokens = list(TOKEN_PATTERN.finditer(paragraph.group()))
            segment_limit = self.max_words - self.overlap_words
            for index in range(0, len(tokens), segment_limit):
                group = tokens[index : index + segment_limit]
                segments.append(
                    _Segment(
                        start=paragraph.start() + group[0].start(),
                        end=paragraph.start() + group[-1].end(),
                        words=len(group),
                    )
                )
        return segments

    def _overlap(self, segments: list[_Segment]) -> list[_Segment]:
        selected: list[_Segment] = []
        words = 0
        for segment in reversed(segments):
            selected.insert(0, segment)
            words += segment.words
            if words >= self.overlap_words:
                break
        return selected

    @staticmethod
    def _record(document: DocumentRecord, group: list[_Segment], ordinal: int) -> ChunkRecord:
        start, end = group[0].start, group[-1].end
        text = document.text[start:end]
        words = len(TOKEN_PATTERN.findall(text))
        return ChunkRecord(
            chunk_id=sha256(f"{document.document_id}:{ordinal}:{text}".encode()).hexdigest(),
            document_id=document.document_id,
            text=text,
            title=document.title,
            ordinal=ordinal,
            start_char=start,
            end_char=end,
            token_estimate=words,
            metadata={
                "source_uri": document.source_uri,
                "heading_path": "",
                "word_count": str(words),
                "overlap_words": "0",
            },
        )

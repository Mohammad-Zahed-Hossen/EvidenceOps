"""Deterministic, structure-aware Markdown chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from evidenceops.domain.errors import ChunkingError
from evidenceops.domain.models import ChunkRecord, DocumentRecord

WORD_PATTERN = re.compile(r"\S+")
HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
FENCE_PATTERN = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


class DocumentChunker(Protocol):
    def chunk(self, document: DocumentRecord) -> list[ChunkRecord]: ...


@dataclass(frozen=True)
class _Block:
    text: str
    start: int
    end: int
    headings: tuple[tuple[int, str], ...]
    code: bool = False
    language: str = ""
    unclosed: bool = False


class MarkdownChunker:
    def __init__(
        self, target_words: int = 500, max_words: int = 600, overlap_words: int = 60
    ) -> None:
        if (
            not 350 <= target_words <= 600
            or not 350 <= max_words <= 600
            or target_words > max_words
        ):
            raise ValueError("target_words and max_words must be within 350 to 600")
        if not 50 <= overlap_words <= 80 or overlap_words >= target_words:
            raise ValueError("overlap_words must be between 50 and 80 and below target_words")
        self.target_words, self.max_words, self.overlap_words = (
            target_words,
            max_words,
            overlap_words,
        )

    def chunk(self, document: DocumentRecord) -> list[ChunkRecord]:
        if document.source_type != "markdown":
            raise ChunkingError("only markdown documents are supported")
        blocks = self._blocks(document.text)
        if not blocks:
            raise ChunkingError("document produced no chunkable content")
        groups: list[list[_Block]] = []
        current: list[_Block] = []
        words = 0
        for block in blocks:
            count = self._words(block.text)
            if current and words + count > self.max_words and not block.code:
                groups.append(current)
                current, words = [], 0
            current.append(block)
            words += count
            if block.code and count > self.max_words:
                groups.append(current)
                current, words = [], 0
        if current:
            groups.append(current)
        return self._records(document, groups)

    def _records(self, document: DocumentRecord, groups: list[list[_Block]]) -> list[ChunkRecord]:
        records: list[ChunkRecord] = []
        previous: list[_Block] = []
        for ordinal, primary in enumerate(groups):
            overlap = self._overlap(previous) if previous else []
            combined = overlap + primary
            start, end = combined[0].start, combined[-1].end
            source = document.text[start:end]
            headings = primary[0].headings
            prefix = self._prefix(headings, source)
            text = prefix + source
            codes = [block.language for block in combined if block.code and block.language]
            oversized = any(
                block.code and self._words(block.text) > self.max_words for block in primary
            )
            metadata = {
                "source_uri": document.source_uri,
                "heading_path": " > ".join(item[1] for item in headings),
                "word_count": str(self._words(source)),
                "overlap_words": str(sum(self._words(block.text) for block in overlap)),
                "contains_code": str(any(block.code for block in combined)).lower(),
                "code_languages": ",".join(dict.fromkeys(codes)),
                "oversized": str(oversized).lower(),
                "oversized_reason": "fenced_code_block" if oversized else "",
                "unclosed_fence": str(any(block.unclosed for block in combined)).lower(),
            }
            chunk_id = sha256(f"{document.document_id}:{ordinal}:{text}".encode()).hexdigest()
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    text=text,
                    title=document.title,
                    ordinal=ordinal,
                    start_char=start,
                    end_char=end,
                    token_estimate=max(1, self._words(source)),
                    metadata=metadata,
                )
            )
            previous = primary
        return records

    def _blocks(self, text: str) -> list[_Block]:
        lines = text.splitlines(keepends=True)
        blocks: list[_Block] = []
        headings: list[tuple[int, str]] = []
        offset = 0
        index = 0
        while index < len(lines):
            line = lines[index]
            fence = FENCE_PATTERN.match(line)
            heading = HEADING_PATTERN.match(line)
            if heading:
                level, title = len(heading.group(1)), heading.group(2).strip()
                headings = [h for h in headings if h[0] < level] + [(level, title)]
                offset += len(line)
                index += 1
                continue
            start = offset
            if fence:
                marker, language = (
                    fence.group(1),
                    fence.group(2).strip().split(" ")[0] if fence.group(2).strip() else "",
                )
                character = marker[0]
                length = len(marker)
                parts = [line]
                offset += len(line)
                index += 1
                closed = False
                while index < len(lines):
                    candidate = lines[index]
                    parts.append(candidate)
                    offset += len(candidate)
                    index += 1
                    close = FENCE_PATTERN.match(candidate)
                    if close and close.group(1)[0] == character and len(close.group(1)) >= length:
                        closed = True
                        break
                blocks.append(
                    _Block(
                        "".join(parts), start, offset, tuple(headings), True, language, not closed
                    )
                )
                continue
            parts = [line]
            offset += len(line)
            index += 1
            while (
                index < len(lines)
                and not HEADING_PATTERN.match(lines[index])
                and not FENCE_PATTERN.match(lines[index])
                and lines[index].strip()
            ):
                parts.append(lines[index])
                offset += len(lines[index])
                index += 1
            value = "".join(parts)
            if value.strip():
                blocks.append(_Block(value, start, offset, tuple(headings)))
        return blocks

    def _overlap(self, blocks: list[_Block]) -> list[_Block]:
        selected: list[_Block] = []
        words = 0
        for block in reversed(blocks):
            if block.code:
                continue
            selected.insert(0, block)
            words += self._words(block.text)
            if words >= self.overlap_words:
                break
        return selected

    @staticmethod
    def _words(text: str) -> int:
        return len(WORD_PATTERN.findall(text))

    @staticmethod
    def _prefix(headings: tuple[tuple[int, str], ...], source: str) -> str:
        lines = [f"{'#' * level} {title}" for level, title in headings]
        if lines and not source.lstrip().startswith(lines[-1]):
            return "\n\n".join(lines) + "\n\n"
        return ""

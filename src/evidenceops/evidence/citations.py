"""Deterministic citation assignment and validation for grounded answers."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ConfigDict, Field

from evidenceops.domain.models import DomainModel, EvidenceRecord

_RE_CITATION = re.compile(r"\[(C[0-9]+)\]")
_RE_POTENTIAL_MALFORMED = re.compile(r"\[([cC]itation\s*[0-9]+|[cC][0-9]+|[0-9]+)\]")


class CitationValidationResult(DomainModel):
    """Result of validating citation references in a generated answer."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    cited_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def assign_citations(evidence: Sequence[EvidenceRecord]) -> list[EvidenceRecord]:
    """Assign deterministic sequential citation IDs [C1], [C2], ... to evidence."""
    assigned: list[EvidenceRecord] = []
    for idx, e in enumerate(evidence, start=1):
        record = EvidenceRecord(
            chunk_id=e.chunk_id,
            document_id=e.document_id,
            title=e.title,
            source_uri=e.source_uri,
            text=e.text,
            retrieval_method=e.retrieval_method,
            retrieval_rank=e.retrieval_rank,
            retrieval_score=e.retrieval_score,
            rerank_score=e.rerank_score,
            citation_id=f"C{idx}",
            metadata=dict(e.metadata),
        )
        assigned.append(record)
    return assigned


def extract_inline_citations(text: str) -> list[str]:
    """Extract citations in stable first-use order from generated answer text."""
    matches = _RE_CITATION.findall(text)
    seen: set[str] = set()
    ordered: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def validate_answer_citations(
    answer: str,
    allowed_citation_ids: set[str],
    require_citations: bool = True,
) -> CitationValidationResult:
    """Validate that every citation in the answer belongs to the allowed set and satisfies bounds.

    Returns a structured validation result indicating validity, cited IDs, and any errors.
    """
    errors: list[str] = []
    cited_ids = extract_inline_citations(answer)

    # Check for unknown citation IDs
    for cid in cited_ids:
        if cid not in allowed_citation_ids:
            errors.append(f"Unknown citation ID [{cid}] not present in provided context.")

    # Check requirement
    if require_citations and not cited_ids:
        errors.append("Factual grounded answer is missing required citation references.")

    # Check for malformed citations (e.g. [citation 1], [c1], [1])
    for match in _RE_POTENTIAL_MALFORMED.finditer(answer):
        token = match.group(0)
        if not _RE_CITATION.fullmatch(token):
            errors.append(
                f"Malformed citation token '{token}'; citations must match [C1], [C2], etc."
            )

    is_valid = len(errors) == 0
    return CitationValidationResult(is_valid=is_valid, cited_ids=cited_ids, errors=errors)

"""Deterministic evidence sufficiency scoring implementing SSOT Section 5."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ConfigDict, Field

from evidenceops.domain.enums import EvidenceStatus
from evidenceops.domain.models import DomainModel, EvidenceRecord

_STOP_WORDS = {
    "a",
    "an",
    "the",
    "in",
    "on",
    "at",
    "for",
    "to",
    "of",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "this",
    "that",
    "it",
    "with",
    "as",
    "by",
    "from",
    "what",
    "how",
    "which",
    "do",
    "does",
    "did",
    "can",
    "could",
    "should",
    "would",
}


class SufficiencyEvaluationResult(DomainModel):
    """Structured output of deterministic evidence sufficiency evaluation."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceStatus
    composite_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    diversity_score: float = Field(ge=0.0, le=1.0)
    answerability_score: float = Field(ge=0.0, le=1.0)


def evaluate_sufficiency(
    query: str,
    evidence: Sequence[EvidenceRecord],
    sufficient_threshold: float = 0.72,
    insufficient_threshold: float = 0.35,
) -> SufficiencyEvaluationResult:
    """Evaluate evidence sufficiency using the composite formula:

    S = 0.45R + 0.25C + 0.15D + 0.15A

    Where:
    - R: normalized relevance in [0, 1]
    - C: query keyword coverage in [0, 1]
    - D: document/section diversity in [0, 1]
    - A: extractive answerability heuristic in [0, 1]
    """
    if not evidence:
        return SufficiencyEvaluationResult(
            status=EvidenceStatus.INSUFFICIENT,
            composite_score=0.0,
            relevance_score=0.0,
            coverage_score=0.0,
            diversity_score=0.0,
            answerability_score=0.0,
        )

    # 1. Relevance Score (R)
    top_candidates = evidence[:5]
    rerank_scores = [e.rerank_score for e in top_candidates if e.rerank_score is not None]
    if rerank_scores:
        # Average top rerank scores clamped to [0, 1]
        r_score = max(0.0, min(1.0, sum(rerank_scores) / len(rerank_scores)))
    else:
        # Fallback to rank-based reciprocal score
        r_score = max(
            0.0, min(1.0, 1.0 / (top_candidates[0].retrieval_rank if top_candidates else 1))
        )

    # 2. Coverage Score (C)
    query_tokens = [
        w.lower()
        for w in re.findall(r"\b[a-zA-Z0-9_-]+\b", query)
        if w.lower() not in _STOP_WORDS and len(w) > 2
    ]
    if query_tokens:
        all_text = " ".join(e.text.lower() for e in evidence)
        covered = sum(
            1
            for token in query_tokens
            if token in all_text
            or (token.endswith("s") and len(token) > 3 and token[:-1] in all_text)
            or (token + "s" in all_text)
        )
        c_score = covered / len(query_tokens)
    else:
        c_score = 1.0

    # 3. Diversity Score (D)
    unique_docs = {e.document_id for e in evidence}
    # 2 or more unique documents provides full diversity score
    d_score = min(1.0, len(unique_docs) / 2.0) if len(evidence) > 1 else 0.70

    # 4. Answerability Score (A)
    # Checks for presence of definitive syntax: code blocks, definitions, direct statements
    combined_top_text = " ".join(e.text for e in top_candidates)
    has_code_block = "```" in combined_top_text
    has_definition = bool(
        re.search(
            r"\b(is|are|use|uses|declare|declares|provide|provides|return|returns|configure|configured|configures|support|supports|set|sets|define|defines)\b",
            combined_top_text,
            re.IGNORECASE,
        )
    )
    a_score = 0.50 + (0.30 if has_definition else 0.0) + (0.20 if has_code_block else 0.0)
    a_score = min(1.0, a_score)

    composite = 0.45 * r_score + 0.25 * c_score + 0.15 * d_score + 0.15 * a_score
    composite = max(0.0, min(1.0, composite))

    if composite >= sufficient_threshold:
        status = EvidenceStatus.SUFFICIENT
    else:
        status = EvidenceStatus.INSUFFICIENT

    return SufficiencyEvaluationResult(
        status=status,
        composite_score=composite,
        relevance_score=r_score,
        coverage_score=c_score,
        diversity_score=d_score,
        answerability_score=a_score,
    )

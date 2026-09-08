"""In-memory, deterministic fixture adapters for LiteBridge evaluation."""

from __future__ import annotations

import re
from typing import Any

from evidenceops.bridge.contracts import RetrievalPolicy, SourceKind
from evidenceops.bridge.ports import EvidenceRetriever, RawEvidenceCandidate, RetrievalBatch
from evidenceops.retrieval.service import (
    DocumentationSearchResult,
    SearchDocumentationRequest,
)

STOPWORDS = {
    "a",
    "an",
    "the",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "what",
    "how",
    "does",
    "do",
    "and",
    "or",
}


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase alpha tokens excluding stopwords."""
    raw_tokens = re.findall(r"[a-z0-9_.\-]+", text.lower())
    return {t for t in raw_tokens if t not in STOPWORDS and len(t) > 1}


def _calculate_relevance(query_tokens: set[str], text: str, title: str = "") -> float:
    """Calculate overlap relevance score."""
    if not query_tokens:
        return 0.0
    text_lower = text.lower()
    title_lower = title.lower()
    score = 0.0
    for tok in query_tokens:
        if tok in title_lower:
            score += 2.0
        elif tok in text_lower:
            score += 1.0
    return score


class FixtureLocalRetriever(EvidenceRetriever):
    """Deterministic local document fixture retriever."""

    def __init__(
        self,
        records: list[dict[str, Any]],
        source_id: str = "fixture_local_docs",
    ) -> None:
        self._records = records
        self._source_id = source_id

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        query_tokens = _tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in self._records:
            title = r.get("metadata", {}).get("title", "")
            rel = _calculate_relevance(query_tokens, r["text"], title)
            if rel > 0.0:
                scored.append((rel, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: policy.max_evidence_items]

        candidates: list[RawEvidenceCandidate] = []
        for rank, (score_val, r) in enumerate(top, start=1):
            cand = RawEvidenceCandidate(
                candidate_id=r["evidence_id"],
                source_kind=SourceKind.LOCAL_DOCUMENT,
                source_id=self._source_id,
                document_id=r["source_uri"],
                chunk_id=r["evidence_id"],
                title=r.get("metadata", {}).get("title", ""),
                section=r.get("metadata", {}).get("section", ""),
                source_label=r["source_uri"],
                text=r["text"],
                retrieval_route="local_fixture",
                rank=rank,
                score=score_val,
                canonical_url=None,
            )
            candidates.append(cand)

        return RetrievalBatch(
            candidates=tuple(candidates),
            retrieval_calls=1,
            web_calls=0,
            retrieval_route="local_fixture",
        )


class FixtureWebSearchAdapter(EvidenceRetriever):
    """Deterministic web snippet fixture retriever with canonical HTTPS URLs."""

    def __init__(
        self,
        records: list[dict[str, Any]],
        source_id: str = "fixture_web_search",
    ) -> None:
        self._records = records
        self._source_id = source_id

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        query_tokens = _tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in self._records:
            title = r.get("metadata", {}).get("title", "")
            rel = _calculate_relevance(query_tokens, r["text"], title)
            if rel > 0.0:
                scored.append((rel, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: policy.max_evidence_items]

        candidates: list[RawEvidenceCandidate] = []
        for rank, (score_val, r) in enumerate(top, start=1):
            cand = RawEvidenceCandidate(
                candidate_id=r["evidence_id"],
                source_kind=SourceKind.WEB_SEARCH_SNIPPET,
                source_id=self._source_id,
                document_id=r["source_uri"],
                chunk_id=r["evidence_id"],
                title=r.get("metadata", {}).get("title", ""),
                section="",
                source_label=r["source_uri"],
                text=r["text"],
                retrieval_route="web_fixture",
                rank=rank,
                score=score_val,
                canonical_url=r["source_uri"],
            )
            candidates.append(cand)

        return RetrievalBatch(
            candidates=tuple(candidates),
            retrieval_calls=1,
            web_calls=1,
            retrieval_route="web_fixture",
        )


class FakeLocalDocumentationService:
    """Fake EvidenceOps LocalDocumentationService for adapter conformance testing."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def search(self, req: SearchDocumentationRequest) -> tuple[DocumentationSearchResult, ...]:
        query_tokens = _tokenize(req.query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in self._records:
            title = r.get("metadata", {}).get("title", "")
            rel = _calculate_relevance(query_tokens, r["text"], title)
            if rel > 0.0:
                scored.append((rel, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: req.top_k]

        results: list[DocumentationSearchResult] = []
        for rank, (score_val, r) in enumerate(top, start=1):
            item = DocumentationSearchResult(
                chunk_id=r["evidence_id"],
                document_id=r["source_uri"],
                title=r.get("metadata", {}).get("title", ""),
                source_uri=r["source_uri"],
                heading_path=r.get("metadata", {}).get("section", ""),
                excerpt=r["text"],
                rank=rank,
                score=score_val,
                retrieval_method="hybrid",
            )
            results.append(item)
        return tuple(results)

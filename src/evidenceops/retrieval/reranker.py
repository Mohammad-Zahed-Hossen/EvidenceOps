import math
from typing import Any

from evidenceops.domain.errors import RerankingError, RetrievalQueryError
from evidenceops.retrieval.contracts import RetrievalResult


def reorder_rerank_results(
    candidates: tuple[RetrievalResult, ...],
    scored_chunk_ids: tuple[tuple[str, float], ...],
    *,
    limit: int,
) -> tuple[RetrievalResult, ...]:
    if limit < 1:
        raise RetrievalQueryError("rerank limit must be positive")
    by_id = {candidate.chunk.chunk_id: candidate for candidate in candidates}

    # Validate and organize scored pairs
    seen: set[str] = set()
    validated_scored: list[tuple[RetrievalResult, float]] = []
    for chunk_id, rerank_score in scored_chunk_ids:
        if not math.isfinite(rerank_score):
            raise RerankingError(f"malformed non-finite reranker score for chunk {chunk_id}")
        if chunk_id in seen:
            raise RerankingError(f"reranker returned duplicate chunk identifier: {chunk_id}")
        if chunk_id not in by_id:
            raise RerankingError(f"reranker returned unknown chunk identifier: {chunk_id}")
        seen.add(chunk_id)
        validated_scored.append((by_id[chunk_id], float(rerank_score)))

    # Deterministic tie-breaking: descending score, then initial candidate rank, then chunk_id
    ordered = sorted(
        validated_scored,
        key=lambda item: (-item[1], item[0].rank, item[0].chunk.chunk_id),
    )[:limit]

    results: list[RetrievalResult] = []
    for rank, (candidate, score) in enumerate(ordered, start=1):
        updated_meta = dict(candidate.metadata)
        updated_meta["rerank_score"] = str(score)
        results.append(
            candidate.model_copy(
                update={
                    "retrieval_method": "reranked",
                    "rank": rank,
                    "score": score,
                    "metadata": updated_meta,
                }
            )
        )
    return tuple(results)


class FlashRankReranker:
    """Bounded lazy FlashRank wrapper retaining retrieval provenance."""

    def __init__(
        self,
        model_name: str = "ms-marco-TinyBERT-L-2-v2",
        max_candidates: int = 20,
    ) -> None:
        self.model_name = model_name
        self.max_candidates = max_candidates
        self._ranker: Any = None

    def _load(self) -> Any:
        if self._ranker is None:
            try:
                from flashrank import Ranker

                self._ranker = Ranker(model_name=self.model_name)
            except Exception as exc:
                raise RerankingError("local reranker model is unavailable") from exc
        return self._ranker

    def rerank(
        self, query: str, candidates: tuple[RetrievalResult, ...], limit: int
    ) -> tuple[RetrievalResult, ...]:
        if not query.strip():
            raise RetrievalQueryError("reranker query must not be empty")
        if not candidates:
            raise RetrievalQueryError("reranker candidates must not be empty")
        if limit < 1:
            raise RetrievalQueryError("reranker limit must be positive")

        selected = candidates[: self.max_candidates]
        try:
            from flashrank import RerankRequest

            passages = [{"id": item.chunk.chunk_id, "text": item.chunk.text} for item in selected]
            ranked = self._load().rerank(RerankRequest(query=query, passages=passages))
            scores = tuple((str(item["id"]), float(item["score"])) for item in ranked)
        except (RetrievalQueryError, RerankingError):
            raise
        except Exception as exc:
            raise RerankingError("reranking inference failed") from exc
        return reorder_rerank_results(selected, scores, limit=limit)

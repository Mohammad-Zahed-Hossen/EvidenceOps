from evidenceops.domain.errors import RetrievalQueryError
from evidenceops.retrieval.contracts import DenseRetriever, RetrievalResult, SparseRetriever


def reciprocal_rank_fusion(
    sparse: tuple[RetrievalResult, ...],
    dense: tuple[RetrievalResult, ...],
    *,
    limit: int,
    k: int = 60,
) -> tuple[RetrievalResult, ...]:
    if limit < 1:
        raise RetrievalQueryError("limit must be positive")
    if k < 1:
        raise ValueError("k must be positive")

    merged: dict[str, dict[str, RetrievalResult]] = {}
    for method, results in (("sparse", sparse), ("dense", dense)):
        seen_in_route: set[str] = set()
        for result in results:
            cid = result.chunk.chunk_id
            if cid in seen_in_route:
                # Retain the highest/first occurrence within the route
                continue
            seen_in_route.add(cid)
            merged.setdefault(cid, {})[method] = result

    fused: list[RetrievalResult] = []
    for _chunk_id, components in merged.items():
        sparse_result = components.get("sparse")
        dense_result = components.get("dense")
        score = sum(1.0 / (k + item.rank) for item in components.values())
        base = sparse_result or dense_result
        assert base is not None
        inherited_meta = dict(base.metadata)
        fused.append(
            RetrievalResult(
                chunk=base.chunk,
                retrieval_method="hybrid",
                rank=1,
                score=score,
                sparse_rank=sparse_result.rank if sparse_result else None,
                dense_rank=dense_result.rank if dense_result else None,
                sparse_score=sparse_result.score if sparse_result else None,
                dense_score=dense_result.score if dense_result else None,
                metadata=inherited_meta,
            )
        )

    ordered = sorted(
        fused,
        key=lambda item: (
            -item.score,
            min(rank for rank in (item.sparse_rank, item.dense_rank) if rank is not None),
            item.chunk.chunk_id,
        ),
    )[:limit]
    return tuple(
        item.model_copy(update={"rank": rank}) for rank, item in enumerate(ordered, start=1)
    )


class HybridRetriever:
    """Orchestrates sparse and dense retrieval and fuses candidates with deterministic RRF."""

    def __init__(
        self,
        sparse_retriever: SparseRetriever,
        dense_retriever: DenseRetriever,
        *,
        top_k_sparse: int = 20,
        top_k_dense: int = 20,
        top_k_hybrid: int = 20,
        rrf_k: int = 60,
    ) -> None:
        self.sparse_retriever = sparse_retriever
        self.dense_retriever = dense_retriever
        self.top_k_sparse = top_k_sparse
        self.top_k_dense = top_k_dense
        self.top_k_hybrid = top_k_hybrid
        self.rrf_k = rrf_k

    def search(
        self, query: str, limit: int | None = None, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]:
        if not query.strip():
            raise RetrievalQueryError("query must not be empty")
        effective_limit = limit if limit is not None else self.top_k_hybrid
        if effective_limit < 1:
            raise RetrievalQueryError("limit must be positive")

        sparse_results = self.sparse_retriever.search(query, limit=self.top_k_sparse)
        dense_results = self.dense_retriever.search(query, limit=self.top_k_dense, filters=filters)

        return reciprocal_rank_fusion(
            sparse_results, dense_results, limit=effective_limit, k=self.rrf_k
        )

"""Convert and deduplicate raw retrieval results into canonical evidence records."""

from __future__ import annotations

from collections.abc import Sequence

from evidenceops.domain.models import EvidenceRecord
from evidenceops.retrieval.contracts import RetrievalResult


def adapt_retrieval_results(results: Sequence[RetrievalResult]) -> tuple[EvidenceRecord, ...]:
    """Convert raw RetrievalResult objects into deduplicated canonical EvidenceRecord objects.

    When the same chunk appears from multiple routes:
    - Retains the best applicable retrieval_rank.
    - Merges route provenance in metadata["all_routes"].
    - Preserves deterministic ordering.
    """
    if not results:
        return ()

    deduped: dict[str, EvidenceRecord] = {}

    for res in results:
        cid = res.chunk_id
        source_uri = res.metadata.get("source_uri") or f"docs/{res.document_id}.md"

        if cid not in deduped:
            routes = [res.retrieval_method]
            metadata = dict(res.metadata)
            metadata["all_routes"] = ",".join(routes)

            rerank_val = None
            if "rerank_score" in res.metadata:
                try:
                    rerank_val = float(res.metadata["rerank_score"])
                except (ValueError, TypeError):
                    rerank_val = None

            record = EvidenceRecord(
                chunk_id=cid,
                document_id=res.document_id,
                title=res.chunk.title,
                source_uri=source_uri,
                text=res.chunk.text,
                retrieval_method=res.retrieval_method,
                retrieval_rank=res.rank,
                retrieval_score=res.score,
                rerank_score=rerank_val,
                citation_id=f"C{len(deduped) + 1}",
                metadata=metadata,
            )
            deduped[cid] = record
        else:
            existing = deduped[cid]
            # Merge route provenance
            current_routes = set(existing.metadata.get("all_routes", "").split(","))
            current_routes.add(res.retrieval_method)
            merged_routes = ",".join(sorted(current_routes))

            # Retain best rank and scores
            best_rank = min(existing.retrieval_rank, res.rank)
            best_score = max(existing.retrieval_score, res.score)
            res_rerank = None
            if "rerank_score" in res.metadata:
                try:
                    res_rerank = float(res.metadata["rerank_score"])
                except (ValueError, TypeError):
                    res_rerank = None

            best_rerank = (
                max(existing.rerank_score or 0.0, res_rerank or 0.0)
                if (existing.rerank_score is not None or res_rerank is not None)
                else None
            )

            updated_metadata = dict(existing.metadata)
            updated_metadata["all_routes"] = merged_routes

            deduped[cid] = EvidenceRecord(
                chunk_id=cid,
                document_id=existing.document_id,
                title=existing.title,
                source_uri=existing.source_uri,
                text=existing.text,
                retrieval_method=existing.retrieval_method,
                retrieval_rank=best_rank,
                retrieval_score=best_score,
                rerank_score=best_rerank,
                citation_id=existing.citation_id,
                metadata=updated_metadata,
            )

    # Sort deterministically by rank then chunk_id
    sorted_records = sorted(deduped.values(), key=lambda r: (r.retrieval_rank, r.chunk_id))

    # Reassign sequential citation IDs based on final sorted order
    reassigned = [
        EvidenceRecord(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            title=r.title,
            source_uri=r.source_uri,
            text=r.text,
            retrieval_method=r.retrieval_method,
            retrieval_rank=r.retrieval_rank,
            retrieval_score=r.retrieval_score,
            rerank_score=r.rerank_score,
            citation_id=f"C{idx}",
            metadata=r.metadata,
        )
        for idx, r in enumerate(sorted_records, start=1)
    ]

    return tuple(reassigned)

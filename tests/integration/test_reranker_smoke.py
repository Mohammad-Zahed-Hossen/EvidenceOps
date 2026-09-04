import pytest

from evidenceops.domain.models import ChunkRecord
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.reranker import FlashRankReranker


@pytest.mark.real_model
def test_real_flashrank_model_smoke() -> None:
    c1 = ChunkRecord(
        chunk_id="chunk-qdrant",
        document_id="doc-1",
        text="Qdrant is a vector database for similarity search.",
        title="Qdrant",
        ordinal=0,
        start_char=0,
        end_char=50,
        token_estimate=8,
        metadata={"source_type": "markdown"},
    )
    c2 = ChunkRecord(
        chunk_id="chunk-weather",
        document_id="doc-2",
        text="The weather in Paris is sunny today.",
        title="Weather",
        ordinal=0,
        start_char=0,
        end_char=36,
        token_estimate=7,
        metadata={"source_type": "markdown"},
    )

    r1 = RetrievalResult(
        chunk=c1,
        retrieval_method="hybrid",
        rank=1,
        score=0.03,
        metadata={"source_type": "markdown"},
    )
    r2 = RetrievalResult(
        chunk=c2,
        retrieval_method="hybrid",
        rank=2,
        score=0.02,
        metadata={"source_type": "markdown"},
    )

    reranker = FlashRankReranker(model_name="ms-marco-TinyBERT-L-2-v2")
    reranked = reranker.rerank("vector database search", (r2, r1), limit=2)

    assert len(reranked) == 2
    # chunk-qdrant should be ranked first by relevance
    assert reranked[0].chunk_id == "chunk-qdrant"
    assert reranked[0].retrieval_method == "reranked"
    assert reranked[0].rank == 1
    assert float(reranked[0].metadata["rerank_score"]) > float(reranked[1].metadata["rerank_score"])

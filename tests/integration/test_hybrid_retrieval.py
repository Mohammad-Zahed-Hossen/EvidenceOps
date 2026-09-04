import pytest

from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.bm25 import Bm25IndexBuilder
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.hybrid import HybridRetriever


class FakeDenseRetrieverForIntegration:
    def __init__(self, chunks: tuple[ChunkRecord, ...]) -> None:
        self.chunks = chunks

    def search(
        self, query: str, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]:
        # Return chunks in reverse order with synthetic cosine scores
        results = []
        for rank, chunk in enumerate(reversed(self.chunks), start=1):
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    retrieval_method="dense",
                    rank=rank,
                    score=1.0 - (rank * 0.1),
                    dense_rank=rank,
                    dense_score=1.0 - (rank * 0.1),
                    metadata=dict(chunk.metadata),
                )
            )
            if len(results) == limit:
                break
        return tuple(results)


def test_hybrid_retrieval_integration(tmp_path) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")

    c1 = ChunkRecord(
        chunk_id="chunk-python",
        document_id="doc-1",
        text="Python is an interpreted programming language.",
        title="Python Overview",
        ordinal=0,
        start_char=0,
        end_char=46,
        token_estimate=6,
        metadata={"source_type": "markdown"},
    )
    c2 = ChunkRecord(
        chunk_id="chunk-qdrant",
        document_id="doc-1",
        text="Qdrant provides vector indexing and payload search in Python.",
        title="Qdrant Overview",
        ordinal=1,
        start_char=47,
        end_char=108,
        token_estimate=9,
        metadata={"source_type": "markdown"},
    )
    c3 = ChunkRecord(
        chunk_id="chunk-fastembed",
        document_id="doc-1",
        text="FastEmbed runs local embeddings in Python.",
        title="FastEmbed Overview",
        ordinal=2,
        start_char=109,
        end_char=151,
        token_estimate=6,
        metadata={"source_type": "markdown"},
    )
    doc = DocumentRecord(
        document_id="doc-1",
        source_uri="docs/python.md",
        title="Python Stack",
        source_type="markdown",
        content_sha256="d" * 64,
        text=f"{c1.text}\n{c2.text}\n{c3.text}",
    )
    store.write(ProcessedDocumentArtifact(document=doc, chunks=(c1, c2, c3)))

    # Sparse retriever built from artifact
    bm25_index = Bm25IndexBuilder(store).build()

    # Dense retriever with known rankings
    dense_retriever = FakeDenseRetrieverForIntegration((c1, c2, c3))

    # Hybrid retriever
    hybrid_retriever = HybridRetriever(
        sparse_retriever=bm25_index,
        dense_retriever=dense_retriever,
        top_k_sparse=3,
        top_k_dense=3,
        top_k_hybrid=3,
        rrf_k=60,
    )

    results = hybrid_retriever.search("Qdrant vector", limit=3)
    assert len(results) > 0
    assert all(r.retrieval_method == "hybrid" for r in results)

    # Top result should be chunk-qdrant since it matches query terms in sparse and has dense rank
    top = results[0]
    assert top.chunk_id == "chunk-qdrant"
    assert top.sparse_rank is not None
    expected_score = (1.0 / (60 + top.sparse_rank)) + (1.0 / (60 + top.dense_rank))
    assert top.score == pytest.approx(expected_score)
    assert top.chunk.title == "Qdrant Overview"
    assert top.metadata["source_type"] == "markdown"

"""Local retrieval contracts and implementations for EvidenceOps."""

from evidenceops.retrieval.bm25 import Bm25Index, Bm25IndexBuilder
from evidenceops.retrieval.contracts import (
    DenseRetriever,
    HybridRetrieverProtocol,
    Reranker,
    RetrievalResult,
    SparseRetriever,
)
from evidenceops.retrieval.dense import DenseIndexer, DenseIndexResult, DenseRetrieverService
from evidenceops.retrieval.embeddings import (
    EmbeddingProvider,
    FastEmbedEmbeddingProvider,
    validate_vectors,
)
from evidenceops.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from evidenceops.retrieval.qdrant_store import (
    QdrantChunkStore,
    chunk_payload,
    chunk_point_id,
)
from evidenceops.retrieval.reranker import FlashRankReranker, reorder_rerank_results
from evidenceops.retrieval.sparse_store import (
    JsonSparseIndexStore,
    SparseIndexSnapshot,
    SparseIndexWriteResult,
    fingerprint,
)
from evidenceops.retrieval.tokenizer import DeterministicTokenizer

__all__ = [
    "Bm25Index",
    "Bm25IndexBuilder",
    "DenseIndexResult",
    "DenseIndexer",
    "DenseRetriever",
    "DenseRetrieverService",
    "DeterministicTokenizer",
    "EmbeddingProvider",
    "FastEmbedEmbeddingProvider",
    "FlashRankReranker",
    "HybridRetriever",
    "HybridRetrieverProtocol",
    "JsonSparseIndexStore",
    "QdrantChunkStore",
    "Reranker",
    "RetrievalResult",
    "SparseIndexSnapshot",
    "SparseIndexWriteResult",
    "SparseRetriever",
    "chunk_payload",
    "chunk_point_id",
    "fingerprint",
    "reciprocal_rank_fusion",
    "reorder_rerank_results",
    "validate_vectors",
]

from dataclasses import dataclass

from evidenceops.domain.errors import RetrievalQueryError, VectorStoreError
from evidenceops.domain.models import ChunkRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.embeddings import EmbeddingProvider
from evidenceops.retrieval.qdrant_store import QdrantChunkStore


@dataclass(frozen=True, slots=True)
class DenseIndexResult:
    total_chunks: int
    indexed_points: int
    collection: str


class DenseIndexer:
    """Read persisted Phase 1B processed artifacts and index chunks into local Qdrant."""

    def __init__(
        self,
        artifact_store: JsonProcessedDocumentStore,
        embeddings: EmbeddingProvider,
        store: QdrantChunkStore,
        batch_size: int = 8,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.artifact_store = artifact_store
        self.embeddings = embeddings
        self.store = store
        self.batch_size = batch_size

    def index(self) -> DenseIndexResult:
        paths = sorted(self.artifact_store.root.glob("*.json"), key=lambda path: path.name)
        if not paths:
            raise VectorStoreError("no processed artifacts found to index")

        chunks: list[ChunkRecord] = []
        source_uris: dict[str, str] = {}
        source_types: dict[str, str] = {}
        seen_chunk_ids: set[str] = set()

        for path in paths:
            artifact = self.artifact_store.read(path.stem)
            doc_id = artifact.document.document_id
            source_uris[doc_id] = artifact.document.source_uri
            source_types[doc_id] = artifact.document.source_type
            for chunk in artifact.chunks:
                if chunk.chunk_id in seen_chunk_ids:
                    raise VectorStoreError(
                        f"duplicate chunk identifier across artifacts: {chunk.chunk_id}"
                    )
                seen_chunk_ids.add(chunk.chunk_id)
                chunks.append(chunk)

        total_upserted = 0
        for i in range(0, len(chunks), self.batch_size):
            batch = tuple(chunks[i : i + self.batch_size])
            texts = tuple(c.text for c in batch)
            vectors = self.embeddings.embed_documents(texts)
            count = self.store.upsert(
                batch, vectors, source_uris=source_uris, source_types=source_types
            )
            total_upserted += count

        return DenseIndexResult(
            total_chunks=len(chunks),
            indexed_points=total_upserted,
            collection=self.store.collection,
        )


class DenseRetrieverService:
    def __init__(self, embeddings: EmbeddingProvider, store: QdrantChunkStore) -> None:
        self.embeddings = embeddings
        self.store = store

    def search(
        self, query: str, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]:
        if not query.strip():
            raise RetrievalQueryError("query must not be empty")
        if limit < 1:
            raise RetrievalQueryError("limit must be at least 1")
        vector = self.embeddings.embed_query(query)
        return self.store.search(vector, limit=limit, filters=filters)

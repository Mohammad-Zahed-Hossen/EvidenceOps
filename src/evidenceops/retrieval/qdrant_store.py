"""Deterministic Qdrant point mapping and safe chunk payload creation."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from evidenceops.domain.errors import VectorStoreError
from evidenceops.domain.models import ChunkRecord
from evidenceops.retrieval.contracts import RetrievalResult


def chunk_point_id(chunk_id: str) -> str:
    """Return a stable Qdrant-compatible UUIDv5 while retaining the original ID in payload."""
    return str(uuid5(NAMESPACE_URL, f"evidenceops:chunk:{chunk_id}"))


def chunk_payload(chunk: ChunkRecord, *, source_uri: str, source_type: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "title": chunk.title,
        "source_uri": source_uri,
        "source_type": source_type,
        "text": chunk.text,
        "ordinal": chunk.ordinal,
    }
    heading_path = chunk.metadata.get("heading_path")
    if heading_path:
        payload["heading_path"] = heading_path
    return payload


class QdrantChunkStore:
    """Explicit Qdrant adapter; no in-memory fallback is available in production."""

    def __init__(
        self,
        url: str,
        collection: str,
        dimension: int = 384,
        distance: str = "Cosine",
        timeout: int = 10,
    ) -> None:
        self.url = url
        self.collection = collection
        self.dimension = dimension
        self.distance = distance
        self.timeout = timeout
        self._client: QdrantClient | None = None

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            try:
                self._client = QdrantClient(
                    url=self.url, timeout=self.timeout, check_compatibility=False
                )
            except Exception as exc:
                raise VectorStoreError("local Qdrant client initialization failed") from exc
        return self._client

    def healthcheck(self) -> bool:
        try:
            self._get_client().get_collections()
            return True
        except Exception as exc:
            raise VectorStoreError("local Qdrant service is unavailable") from exc

    def ensure_collection(self) -> None:
        client = self._get_client()
        try:
            if not client.collection_exists(self.collection):
                client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
                )
                return
            config = client.get_collection(self.collection).config.params.vectors
            if not isinstance(config, VectorParams):
                raise VectorStoreError("Qdrant collection vectors config is invalid")
            if config.size != self.dimension:
                raise VectorStoreError(
                    f"Qdrant collection dimension mismatch: "
                    f"expected {self.dimension}, found {config.size}"
                )
            if config.distance != Distance.COSINE:
                raise VectorStoreError(
                    f"Qdrant collection distance mismatch: expected Cosine, found {config.distance}"
                )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Qdrant collection lifecycle check failed") from exc

    def delete_collection(self, collection_name: str) -> None:
        if not collection_name or collection_name != self.collection:
            raise VectorStoreError("cannot delete collection: name mismatch or empty")
        try:
            self._get_client().delete_collection(collection_name=collection_name)
        except Exception as exc:
            raise VectorStoreError("failed to delete Qdrant collection") from exc

    def upsert(
        self,
        chunks: tuple[ChunkRecord, ...],
        vectors: tuple[tuple[float, ...], ...],
        *,
        source_uris: dict[str, str],
        source_types: dict[str, str],
    ) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunk and vector counts differ")
        if any(len(vector) != self.dimension for vector in vectors):
            raise VectorStoreError("embedding dimension does not match configured collection")
        self.ensure_collection()
        points = [
            PointStruct(
                id=chunk_point_id(chunk.chunk_id),
                vector=list(vector),
                payload=chunk_payload(
                    chunk,
                    source_uri=source_uris[chunk.document_id],
                    source_type=source_types[chunk.document_id],
                ),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            self._get_client().upsert(collection_name=self.collection, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError("Qdrant upsert failed") from exc
        return len(points)

    def search(
        self, vector: tuple[float, ...], *, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]:
        if len(vector) != self.dimension:
            raise VectorStoreError("query embedding dimension does not match configured collection")
        if limit < 1:
            raise VectorStoreError("search limit must be at least 1")
        if filters and set(filters) - {"source_type", "document_id"}:
            raise VectorStoreError("unsupported dense retrieval filter")
        query_filter = None
        if filters:
            query_filter = Filter(
                must=[
                    FieldCondition(key=key, match=MatchValue(value=value))
                    for key, value in filters.items()
                ]
            )
        try:
            response = (
                self._get_client()
                .query_points(
                    collection_name=self.collection,
                    query=list(vector),
                    limit=limit,
                    query_filter=query_filter,
                )
                .points
            )
        except Exception as exc:
            raise VectorStoreError("Qdrant dense search failed") from exc
        results: list[RetrievalResult] = []
        ordered_points = sorted(
            response,
            key=lambda item: (
                -float(item.score),
                str((item.payload or {}).get("chunk_id", item.id)),
            ),
        )
        for rank, point in enumerate(ordered_points, start=1):
            payload = point.payload or {}
            try:
                chunk = ChunkRecord(
                    chunk_id=str(payload["chunk_id"]),
                    document_id=str(payload["document_id"]),
                    text=str(payload["text"]),
                    title=str(payload["title"]),
                    ordinal=int(payload["ordinal"]),
                    start_char=0,
                    end_char=len(str(payload["text"])),
                    token_estimate=max(1, len(str(payload["text"]).split())),
                    metadata={"heading_path": str(payload.get("heading_path", ""))},
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise VectorStoreError("Qdrant response payload is invalid") from exc
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    retrieval_method="dense",
                    rank=rank,
                    score=float(point.score),
                    dense_rank=rank,
                    dense_score=float(point.score),
                    metadata={"source_type": str(payload.get("source_type", "unknown"))},
                )
            )
        return tuple(results)

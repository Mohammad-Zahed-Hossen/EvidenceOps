from unittest.mock import MagicMock

import pytest
from qdrant_client.models import Distance, VectorParams

from evidenceops.domain.errors import VectorStoreError
from evidenceops.retrieval.qdrant_store import QdrantChunkStore, chunk_payload, chunk_point_id


def test_point_id_and_payload_are_deterministic_and_allowlisted(chunk_record) -> None:
    id1 = chunk_point_id(chunk_record.chunk_id)
    id2 = chunk_point_id(chunk_record.chunk_id)
    assert id1 == id2
    assert isinstance(id1, str)
    # Check that different chunk_id produces different point_id
    assert chunk_point_id("chunk-2") != id1

    payload = chunk_payload(chunk_record, source_uri="docs/retrieval.md", source_type="markdown")
    assert payload["chunk_id"] == "chunk-1"
    assert payload["heading_path"] == "Retrieval"
    assert set(payload) == {
        "chunk_id",
        "document_id",
        "title",
        "source_uri",
        "source_type",
        "heading_path",
        "text",
        "ordinal",
    }


def test_qdrant_store_validates_dimension_mismatch() -> None:
    store = QdrantChunkStore(url="http://localhost:6333", collection="test_col", dimension=384)
    fake_client = MagicMock()
    fake_client.collection_exists.return_value = True
    fake_info = MagicMock()
    fake_info.config.params.vectors = VectorParams(size=512, distance=Distance.COSINE)
    fake_client.get_collection.return_value = fake_info
    store._client = fake_client

    with pytest.raises(VectorStoreError, match="dimension mismatch"):
        store.ensure_collection()


def test_qdrant_store_validates_distance_mismatch() -> None:
    store = QdrantChunkStore(url="http://localhost:6333", collection="test_col", dimension=384)
    fake_client = MagicMock()
    fake_client.collection_exists.return_value = True
    fake_info = MagicMock()
    fake_info.config.params.vectors = VectorParams(size=384, distance=Distance.DOT)
    fake_client.get_collection.return_value = fake_info
    store._client = fake_client

    with pytest.raises(VectorStoreError, match="distance mismatch"):
        store.ensure_collection()


def test_qdrant_store_rejects_unsupported_filters() -> None:
    store = QdrantChunkStore(url="http://localhost:6333", collection="test_col", dimension=3)
    with pytest.raises(VectorStoreError, match="unsupported dense retrieval filter"):
        store.search((0.1, 0.2, 0.3), limit=5, filters={"unsupported_field": "val"})


def test_qdrant_store_rejects_invalid_limit() -> None:
    store = QdrantChunkStore(url="http://localhost:6333", collection="test_col", dimension=3)
    with pytest.raises(VectorStoreError, match="search limit must be at least 1"):
        store.search((0.1, 0.2, 0.3), limit=0)


def test_qdrant_store_rejects_query_vector_dimension_mismatch() -> None:
    store = QdrantChunkStore(url="http://localhost:6333", collection="test_col", dimension=384)
    with pytest.raises(VectorStoreError, match="query embedding dimension"):
        store.search((0.1, 0.2), limit=5)

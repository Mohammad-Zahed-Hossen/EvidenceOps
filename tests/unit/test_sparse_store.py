import json

import pytest

from evidenceops.domain.errors import SparseIndexError
from evidenceops.retrieval.sparse_store import (
    JsonSparseIndexStore,
    SparseIndexSnapshot,
    fingerprint,
)


def make_snapshot(index_id: str = "sample-v1") -> SparseIndexSnapshot:
    chunk_ids = ("chunk-1", "chunk-2")
    document_ids = ("doc-1", "doc-1")
    corpus = (("qdrant", "vector"), ("fastembed", "embedding"))
    return SparseIndexSnapshot(
        index_id=index_id,
        tokenizer_version="1.0",
        bm25_k1=1.5,
        bm25_b=0.75,
        chunk_ids=chunk_ids,
        document_ids=document_ids,
        tokenized_corpus=corpus,
        corpus_fingerprint=fingerprint([("chunk-1", "doc-1"), ("chunk-2", "doc-1")]),
        configuration_fingerprint=fingerprint({"tokenizer_version": "1.0", "k1": 1.5, "b": 0.75}),
    )


def test_store_writes_deterministic_bytes_and_loads_snapshot(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    snap = make_snapshot()
    first = store.write(snap)
    second = store.write(snap)

    assert first.disposition == "created"
    assert second.disposition == "unchanged"
    loaded = store.load("sample-v1")
    assert loaded == snap


def test_store_persisted_bytes_are_deterministic(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    snap = make_snapshot()
    res = store.write(snap)
    bytes1 = res.path.read_bytes()

    # Create another store and snapshot in a different directory
    other_dir = tmp_path / "other"
    other_store = JsonSparseIndexStore(other_dir)
    res2 = other_store.write(snap)
    bytes2 = res2.path.read_bytes()

    assert bytes1 == bytes2
    assert bytes1.endswith(b"\n")


def test_store_rejects_unsafe_index_identifier(tmp_path) -> None:
    with pytest.raises(SparseIndexError, match="invalid sparse index identifier"):
        JsonSparseIndexStore(tmp_path).load("../escape")


def test_store_rejects_conflicting_index(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    snap1 = make_snapshot("idx-1")
    store.write(snap1)

    # Different snapshot with the same index_id
    snap2 = snap1.model_copy(update={"bm25_k1": 2.0})
    with pytest.raises(SparseIndexError, match="sparse index already exists"):
        store.write(snap2)


def test_store_rejects_corrupt_json(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ corrupt json ...", encoding="utf-8")

    with pytest.raises(SparseIndexError, match="snapshot is invalid"):
        store.load("bad")


def test_store_rejects_unknown_schema_version(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    snap = make_snapshot("unsupported-v1")
    data = snap.model_dump(mode="json")
    data["schema_version"] = "999.0"
    (tmp_path / "unsupported-v1.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SparseIndexError, match="unsupported sparse index schema version"):
        store.load("unsupported-v1")


def test_store_rejects_duplicate_chunk_ids_in_corpus(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    snap = make_snapshot("dup-v1")
    data = snap.model_dump(mode="json")
    data["chunk_ids"] = ["chunk-1", "chunk-1"]
    data["document_ids"] = ["doc-1", "doc-1"]
    data["tokenized_corpus"] = [["a"], ["b"]]
    (tmp_path / "dup-v1.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SparseIndexError, match="inconsistent corpus data"):
        store.load("dup-v1")


def test_store_rejects_missing_file(tmp_path) -> None:
    store = JsonSparseIndexStore(tmp_path)
    with pytest.raises(SparseIndexError, match="not found"):
        store.load("nonexistent")

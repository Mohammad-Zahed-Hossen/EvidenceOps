"""In-process BM25 built exclusively from persisted processed artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from evidenceops.domain.errors import RetrievalQueryError, SparseIndexError
from evidenceops.domain.models import ChunkRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.sparse_store import SparseIndexSnapshot, fingerprint
from evidenceops.retrieval.tokenizer import DeterministicTokenizer


@dataclass(frozen=True, slots=True)
class Bm25Index:
    chunk_ids: tuple[str, ...]
    chunks: tuple[ChunkRecord, ...]
    tokenized_corpus: tuple[tuple[str, ...], ...]
    _runtime: BM25Okapi
    tokenizer: DeterministicTokenizer

    def search(self, query: str, limit: int) -> tuple[RetrievalResult, ...]:
        if not query.strip() or limit < 1:
            raise RetrievalQueryError("query and limit must be valid")
        tokens = self.tokenizer.tokenize(query)
        if not tokens:
            raise RetrievalQueryError("tokenized query must not be empty")
        scores = self._runtime.get_scores(list(tokens))
        ranked = sorted(enumerate(scores), key=lambda item: (-float(item[1]), item[0]))[:limit]
        results: list[RetrievalResult] = []
        for rank, (ordinal, score) in enumerate(ranked, start=1):
            numeric_score = float(score)
            if not math.isfinite(numeric_score):
                raise RetrievalQueryError("BM25 produced a non-finite score")
            chunk = self.chunks[ordinal]
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    retrieval_method="sparse",
                    rank=rank,
                    score=numeric_score,
                    sparse_rank=rank,
                    sparse_score=numeric_score,
                    metadata={"source_type": chunk.metadata.get("source_type", "unknown")},
                )
            )
        return tuple(results)


class Bm25IndexBuilder:
    def __init__(
        self, artifact_store: JsonProcessedDocumentStore, *, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.artifact_store = artifact_store
        self.k1 = k1
        self.b = b
        self.tokenizer = DeterministicTokenizer()

    def build(self) -> Bm25Index:
        paths = sorted(self.artifact_store.root.glob("*.json"), key=lambda path: path.name)
        if not paths:
            raise SparseIndexError("no processed artifacts were found")
        chunks: list[ChunkRecord] = []
        document_ids: set[str] = set()
        chunk_ids: set[str] = set()
        for path in paths:
            artifact = self.artifact_store.read(path.stem)
            if artifact.document.document_id in document_ids:
                raise SparseIndexError("duplicate document identifier in artifacts")
            document_ids.add(artifact.document.document_id)
            for chunk in artifact.chunks:
                if chunk.chunk_id in chunk_ids:
                    raise SparseIndexError("duplicate chunk identifier in artifacts")
                chunk_ids.add(chunk.chunk_id)
                chunks.append(chunk)
        corpus = tuple(self.tokenizer.tokenize(chunk.text) for chunk in chunks)
        if any(not tokens for tokens in corpus):
            raise SparseIndexError("chunk text produced an empty BM25 token sequence")
        return Bm25Index(
            chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
            chunks=tuple(chunks),
            tokenized_corpus=corpus,
            _runtime=BM25Okapi([list(tokens) for tokens in corpus], k1=self.k1, b=self.b),
            tokenizer=self.tokenizer,
        )

    def snapshot(self, index_id: str) -> SparseIndexSnapshot:
        index = self.build()
        document_ids = tuple(chunk.document_id for chunk in index.chunks)
        corpus_identity = [(chunk.chunk_id, chunk.document_id) for chunk in index.chunks]
        config = {"tokenizer_version": self.tokenizer.version, "k1": self.k1, "b": self.b}
        return SparseIndexSnapshot(
            index_id=index_id,
            tokenizer_version=self.tokenizer.version,
            bm25_k1=self.k1,
            bm25_b=self.b,
            chunk_ids=index.chunk_ids,
            document_ids=document_ids,
            tokenized_corpus=index.tokenized_corpus,
            corpus_fingerprint=fingerprint(corpus_identity),
            configuration_fingerprint=fingerprint(config),
        )

    @classmethod
    def from_snapshot(
        cls, snapshot: SparseIndexSnapshot, artifact_store: JsonProcessedDocumentStore
    ) -> Bm25Index:
        chunk_map: dict[str, ChunkRecord] = {}
        unique_docs = sorted(set(snapshot.document_ids))
        for doc_id in unique_docs:
            try:
                artifact = artifact_store.read(doc_id)
            except Exception as exc:
                raise SparseIndexError(f"cannot resolve artifact for document: {doc_id}") from exc
            for chunk in artifact.chunks:
                chunk_map[chunk.chunk_id] = chunk

        resolved_chunks: list[ChunkRecord] = []
        for cid in snapshot.chunk_ids:
            if cid not in chunk_map:
                raise SparseIndexError(f"unresolved chunk identifier in snapshot: {cid}")
            resolved_chunks.append(chunk_map[cid])

        runtime = BM25Okapi(
            [list(tokens) for tokens in snapshot.tokenized_corpus],
            k1=snapshot.bm25_k1,
            b=snapshot.bm25_b,
        )
        return Bm25Index(
            chunk_ids=snapshot.chunk_ids,
            chunks=tuple(resolved_chunks),
            tokenized_corpus=snapshot.tokenized_corpus,
            _runtime=runtime,
            tokenizer=DeterministicTokenizer(),
        )

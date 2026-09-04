"""Lazy, local embedding adapter and vector validation."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, Protocol

from evidenceops.domain.errors import EmbeddingError


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


def validate_vectors(
    vectors: Iterable[Iterable[float]], expected_dimension: int | None = None
) -> tuple[tuple[float, ...], ...]:
    normalized = tuple(tuple(float(value) for value in vector) for vector in vectors)
    if not normalized or any(not vector for vector in normalized):
        raise EmbeddingError("embedding vectors must not be empty")
    dimension = len(normalized[0])
    if any(len(vector) != dimension for vector in normalized):
        raise EmbeddingError("embedding vectors have inconsistent dimension")
    if expected_dimension is not None and dimension != expected_dimension:
        raise EmbeddingError(
            f"embedding vector dimension mismatch: expected {expected_dimension}, got {dimension}"
        )
    if any(not math.isfinite(value) for vector in normalized for value in vector):
        raise EmbeddingError("embedding vectors must contain finite values")
    return normalized


class FastEmbedEmbeddingProvider:
    """Load FastEmbed only on the first document or query embedding request."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        threads: int = 4,
        expected_dimension: int = 384,
    ) -> None:
        self.model_name = model_name
        self.threads = threads
        self.expected_dimension = expected_dimension
        self._model: Any = None
        self._detected_dimension: int | None = None

    @property
    def detected_dimension(self) -> int | None:
        return self._detected_dimension

    def _load(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name, threads=self.threads)
            except Exception as exc:
                raise EmbeddingError("local embedding model is unavailable") from exc
        return self._model

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("document embedding input must not be empty")
        model = self._load()
        try:
            vectors = validate_vectors(
                model.embed(list(texts)),
                expected_dimension=self.expected_dimension,
            )
            if vectors and self._detected_dimension is None:
                self._detected_dimension = len(vectors[0])
            return vectors
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("document embedding failed") from exc

    def embed_query(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise EmbeddingError("query embedding input must not be empty")
        model = self._load()
        try:
            if hasattr(model, "query_embed"):
                raw = list(model.query_embed([text]))
            else:
                raw = list(model.embed([text]))
            vectors = validate_vectors(raw, expected_dimension=self.expected_dimension)
            if vectors and self._detected_dimension is None:
                self._detected_dimension = len(vectors[0])
            return vectors[0]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("query embedding failed") from exc

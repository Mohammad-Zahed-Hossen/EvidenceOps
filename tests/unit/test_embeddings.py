import pytest

from evidenceops.domain.errors import EmbeddingError
from evidenceops.retrieval.embeddings import (
    FastEmbedEmbeddingProvider,
    validate_vectors,
)


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            raise EmbeddingError("empty input")
        return tuple(tuple(float(i + 1) for i in range(self.dimension)) for _ in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise EmbeddingError("empty query")
        return tuple(0.1 for _ in range(self.dimension))


def test_validate_vectors_success() -> None:
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    res = validate_vectors(vectors, expected_dimension=3)
    assert res == ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6))


def test_validate_vectors_rejects_empty() -> None:
    with pytest.raises(EmbeddingError, match="must not be empty"):
        validate_vectors([])


def test_validate_vectors_rejects_inconsistent_dimension() -> None:
    with pytest.raises(EmbeddingError, match="inconsistent dimension"):
        validate_vectors([[0.1, 0.2], [0.1, 0.2, 0.3]])


def test_validate_vectors_rejects_dimension_mismatch() -> None:
    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        validate_vectors([[0.1, 0.2]], expected_dimension=384)


def test_validate_vectors_rejects_non_finite_values() -> None:
    with pytest.raises(EmbeddingError, match="finite values"):
        validate_vectors([[0.1, float("nan")]])

    with pytest.raises(EmbeddingError, match="finite values"):
        validate_vectors([[0.1, float("inf")]])


def test_fastembed_provider_lazy_loading() -> None:
    # Creating the provider must not load the model or fail
    provider = FastEmbedEmbeddingProvider(model_name="BAAI/bge-small-en-v1.5", threads=4)
    assert provider._model is None
    assert provider.detected_dimension is None


def test_fastembed_provider_rejects_empty_inputs() -> None:
    provider = FastEmbedEmbeddingProvider()
    with pytest.raises(EmbeddingError, match="input must not be empty"):
        provider.embed_documents(())

    with pytest.raises(EmbeddingError, match="input must not be empty"):
        provider.embed_documents(("",))

    with pytest.raises(EmbeddingError, match="input must not be empty"):
        provider.embed_query("")

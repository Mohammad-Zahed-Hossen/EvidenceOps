import pytest

from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider


@pytest.mark.real_model
def test_real_fastembed_model_smoke() -> None:
    provider = FastEmbedEmbeddingProvider(
        model_name="BAAI/bge-small-en-v1.5", threads=4, expected_dimension=384
    )

    doc_vectors = provider.embed_documents(
        ("Vector search in local EvidenceOps.", "CPU-safe embedding generation.")
    )
    assert len(doc_vectors) == 2
    assert len(doc_vectors[0]) == 384
    assert len(doc_vectors[1]) == 384
    assert provider.detected_dimension == 384

    query_vector = provider.embed_query("EvidenceOps retrieval")
    assert len(query_vector) == 384

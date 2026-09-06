from unittest.mock import patch

import pytest

from evidenceops.cli.query import main


def test_cli_rejects_remote_endpoint_before_service_access(capsys):
    with patch("evidenceops.cli.query.build_documentation_service") as factory:
        assert main(["hello", "--ollama-host", "https://example.com/v1", "--json"]) != 0
        factory.assert_not_called()
    assert "example.com" not in capsys.readouterr().out


def test_cli_help_does_not_construct_services():
    with patch("evidenceops.cli.query.build_documentation_service") as factory:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        factory.assert_not_called()


def test_lazy_service_adapter_uses_public_method_and_source_metadata(tmp_path, chunk_record):
    from evidenceops.graph.composition import DocumentationRoute
    from evidenceops.retrieval.service import LocalDocumentationService
    from tests.unit.test_documentation_service import RecordingDenseRetriever, _artifact_store

    dense = RecordingDenseRetriever(chunk_record)
    service = LocalDocumentationService(
        artifact_store=_artifact_store(tmp_path, chunk_record), dense_factory=lambda: dense
    )
    adapter = DocumentationRoute(service, "dense")
    assert service.dense_retriever is None
    results = adapter.search("Qdrant", 5)
    assert dense.calls == [("Qdrant", 5, None)]
    assert results[0].metadata["source_uri"] == "docs/retrieval.md"


def test_embedding_query_offline_flag_reaches_model():
    from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider

    with patch("fastembed.TextEmbedding") as model:
        provider = FastEmbedEmbeddingProvider(local_files_only=True)
        provider._load()
        assert model.call_args.kwargs["local_files_only"] is True


def test_offline_reranker_does_not_download_missing_model(tmp_path):
    from evidenceops.domain.errors import RerankingError
    from evidenceops.retrieval.reranker import FlashRankReranker

    with patch("flashrank.Config.default_cache_dir", str(tmp_path)):
        with patch("flashrank.Ranker") as model:
            with pytest.raises(RerankingError):
                FlashRankReranker(local_files_only=True)._load()
            model.assert_not_called()

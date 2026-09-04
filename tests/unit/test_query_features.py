"""Unit tests for deterministic query feature extraction."""

from __future__ import annotations

import pytest

from evidenceops.controller.features import RegexFeatureExtractor


@pytest.fixture
def extractor() -> RegexFeatureExtractor:
    return RegexFeatureExtractor()


def test_basic_token_and_character_counts(extractor: RegexFeatureExtractor) -> None:
    features = extractor.extract("What is information retrieval?")
    assert features.token_count == 4
    assert features.question_count == 1
    assert features.has_code_terms is False
    assert features.has_comparison_terms is False


def test_code_identifier_detection(extractor: RegexFeatureExtractor) -> None:
    # camelCase or PascalCase
    assert extractor.extract("How does BaseSettings work?").has_code_terms is True
    # snake_case
    assert extractor.extract("What does status_code do?").has_code_terms is True
    # CLI flag
    assert extractor.extract("What is the --timeout option?").has_code_terms is True
    # Dotted symbol
    assert extractor.extract("Explain pydantic.BaseModel inheritance").has_code_terms is True
    # Code fence / backticks
    assert extractor.extract("Usage of `Depends()` in path functions").has_code_terms is True


def test_comparison_terms_detection(extractor: RegexFeatureExtractor) -> None:
    assert extractor.extract("Compare FastAPI vs Flask performance").has_comparison_terms is True
    assert (
        extractor.extract("What is the difference between sparse and dense?").has_comparison_terms
        is True
    )
    assert extractor.extract("Versus comparison of models").has_comparison_terms is True


def test_temporal_terms_detection(extractor: RegexFeatureExtractor) -> None:
    assert extractor.extract("What is the latest release?").has_temporal_terms is True
    assert extractor.extract("Is this feature deprecated in version 2?").has_temporal_terms is True


def test_multi_hop_terms_detection(extractor: RegexFeatureExtractor) -> None:
    assert extractor.extract("How to configure Qdrant with FastEmbed?").has_multi_hop_terms is True
    assert extractor.extract("What are the prerequisites for indexing?").has_multi_hop_terms is True


def test_greeting_and_direct_queries(extractor: RegexFeatureExtractor) -> None:
    greetings = ["Hello", "Hi there!", "Good morning", "Hey"]
    for g in greetings:
        f = extractor.extract(g)
        assert f.predicted_external_knowledge_probability < 0.20

    factual = "What is the default port for Qdrant?"
    assert extractor.extract(factual).predicted_external_knowledge_probability >= 0.70


def test_deterministic_output(extractor: RegexFeatureExtractor) -> None:
    q = "What is the difference between FastAPI dependencies and middleware in version 0.115?"
    f1 = extractor.extract(q)
    f2 = extractor.extract(q)
    assert f1.model_dump() == f2.model_dump()

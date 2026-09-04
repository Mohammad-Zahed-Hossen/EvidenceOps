"""Unit tests for query reformulation and repeat detection."""

from __future__ import annotations

import pytest

from evidenceops.generation.contracts import GenerationResponse
from evidenceops.generation.reformulator import LocalQueryReformulator


class FakeGeneratorClient:
    def __init__(self, returned_content: str) -> None:
        self.returned_content = returned_content

    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        return GenerationResponse(content=self.returned_content)


def test_reformulator_refines_query_and_preserves_identifiers() -> None:
    client = FakeGeneratorClient("FastAPI response status_code parameter declaration")
    reformulator = LocalQueryReformulator(generator_client=client)

    original = "How to set status_code in FastAPI?"
    refined = reformulator.reformulate(original, previous_queries=[original])
    assert "status_code" in refined
    assert refined != original


def test_reformulator_detects_duplicate_and_returns_fallback() -> None:
    # Client returns identical query to original
    original = "How to configure Qdrant?"
    client = FakeGeneratorClient("How to configure Qdrant?")
    reformulator = LocalQueryReformulator(generator_client=client)

    with pytest.raises(ValueError, match="duplicate"):
        reformulator.reformulate(original, previous_queries=[original])

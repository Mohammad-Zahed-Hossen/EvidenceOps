"""Unit tests for individual LangGraph orchestration nodes."""

from __future__ import annotations

import pytest

from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.controller.heuristic import HeuristicRetrievalController
from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import ChunkRecord, EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.nodes import (
    abstain_node,
    controller_decide_node,
    evaluate_evidence_node,
    extract_features_node,
    finalize_node,
    generate_node,
    initialize_node,
    retrieve_node,
    validate_citations_node,
)
from evidenceops.retrieval.contracts import RetrievalResult


class FakeRetriever:
    def __init__(self, chunk: ChunkRecord) -> None:
        self.chunk = chunk

    def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
        return (
            RetrievalResult(
                chunk=self.chunk,
                retrieval_method="sparse",
                rank=1,
                score=2.0,
                metadata={"source_uri": "docs/test.md"},
            ),
        )


class FakeGenerator:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        return GenerationResponse(
            content=self.response_text, prompt_tokens=20, completion_tokens=10
        )


@pytest.fixture
def sample_chunk() -> ChunkRecord:
    return ChunkRecord(
        chunk_id="c1",
        document_id="doc1",
        title="FastAPI Title",
        text="In FastAPI, declare status_code=200 in path operation decorators.",
        start_char=0,
        end_char=50,
        ordinal=0,
        token_estimate=10,
    )


def test_initialize_node() -> None:
    initial_dict = {
        "run_id": "run-init",
        "original_query": "What is FastAPI?",
        "active_query": "What is FastAPI?",
    }
    updated = initialize_node(initial_dict)
    assert updated["status"] == RunStatus.RUNNING


def test_extract_features_node() -> None:
    state = EvidenceOpsState(
        run_id="r1", original_query="pydantic.BaseModel", active_query="pydantic.BaseModel"
    )
    updated = extract_features_node(state.to_langgraph_dict(), extractor=RegexFeatureExtractor())
    assert updated["query_features"]["has_code_terms"] is True


def test_controller_decide_node() -> None:
    state = EvidenceOpsState(run_id="r1", original_query="FastAPI", active_query="FastAPI")
    controller = HeuristicRetrievalController(RegexFeatureExtractor())
    updated = controller_decide_node(state.to_langgraph_dict(), controller=controller)
    assert updated["next_action"] in (
        Action.RETRIEVE_SPARSE,
        Action.RETRIEVE_DENSE,
        Action.RETRIEVE_HYBRID,
    )


def test_retrieve_node_increments_calls(sample_chunk: ChunkRecord) -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="FastAPI",
        active_query="FastAPI",
        route=QueryRoute.SPARSE,
        retrieval_calls=0,
    )
    retriever = FakeRetriever(sample_chunk)
    updated = retrieve_node(state.to_langgraph_dict(), sparse_retriever=retriever)
    assert updated["retrieval_calls"] == 1
    assert len(updated["evidence"]) == 1
    assert updated["evidence"][0]["chunk_id"] == "c1"


def test_evaluate_evidence_node(sample_chunk: ChunkRecord) -> None:
    ev = EvidenceRecord(
        chunk_id="c1",
        document_id="doc1",
        title="Doc",
        source_uri="docs/test.md",
        text=sample_chunk.text,
        retrieval_method="sparse",
        retrieval_rank=1,
        retrieval_score=2.0,
        rerank_score=0.90,
        citation_id="C1",
    )
    state = EvidenceOpsState(
        run_id="r1",
        original_query="What parameter declares status_code in FastAPI?",
        active_query="What parameter declares status_code in FastAPI?",
        evidence=[ev],
    )
    updated = evaluate_evidence_node(state.to_langgraph_dict())
    assert updated["evidence_status"] == EvidenceStatus.SUFFICIENT
    assert updated["sufficiency_score"] >= 0.72


def test_generate_node_produces_answer(sample_chunk: ChunkRecord) -> None:
    ev = EvidenceRecord(
        chunk_id="c1",
        document_id="doc1",
        title="Doc",
        source_uri="docs/test.md",
        text=sample_chunk.text,
        retrieval_method="sparse",
        retrieval_rank=1,
        retrieval_score=2.0,
        citation_id="C1",
    )
    state = EvidenceOpsState(
        run_id="r1",
        original_query="FastAPI status code",
        active_query="FastAPI status code",
        evidence=[ev],
    )
    gen = FakeGenerator("You use status_code [C1].")
    updated = generate_node(state.to_langgraph_dict(), generator_client=gen)
    assert updated["answer"] == "You use status_code [C1]."


def test_validate_citations_node_valid() -> None:
    ev = EvidenceRecord(
        chunk_id="c1",
        document_id="doc1",
        title="Doc",
        source_uri="docs/test.md",
        text="text",
        retrieval_method="sparse",
        retrieval_rank=1,
        retrieval_score=2.0,
        citation_id="C1",
    )
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        evidence=[ev],
        answer="Valid answer [C1].",
    )
    updated = validate_citations_node(state.to_langgraph_dict())
    assert updated["citations"] == ["C1"]
    assert updated["metadata"].get("citation_validation_failed") is not True


def test_validate_citations_node_invalid_triggers_flag() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        evidence=[],
        answer="Invalid answer [C99].",
    )
    updated = validate_citations_node(state.to_langgraph_dict())
    assert updated["metadata"].get("citation_validation_failed") is True


def test_abstain_node_sets_status() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
    )
    updated = abstain_node(state.to_langgraph_dict(), reason="evidence_below_threshold")
    assert updated["status"] == RunStatus.ABSTAINED
    assert updated["abstention_reason"] == "evidence_below_threshold"


def test_finalize_node() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="q",
        active_query="q",
        answer="Final grounded answer [C1].",
        citations=["C1"],
    )
    updated = finalize_node(state.to_langgraph_dict())
    assert updated["status"] == RunStatus.COMPLETED

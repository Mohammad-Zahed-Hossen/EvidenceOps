import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import Action, QueryRoute
from evidenceops.domain.models import RetrievalAttempt
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.generation.prompts import build_citation_correction_prompt, build_grounded_prompt
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.settings import Settings


def test_prompts_enumerate_only_packed_citation_labels():
    context = '<evidence id="C1" chunk_id="a">Source text</evidence>'
    for messages in (
        build_grounded_prompt("question", context),
        build_citation_correction_prompt("question", context, "bad [C2]", ["unknown"]),
    ):
        assert "Allowed citations: [C1]." in messages[-1]["content"]
        assert "one or two sentences" in messages[0]["content"]


@pytest.mark.parametrize(
    "url",
    [
        "ftp://localhost/v1",
        "http://user:secret@localhost/v1",
        "http://localhost/v1?secret=x",
        "http://localhost/v1#x",
    ],
)
def test_local_endpoint_rejects_unsupported_url_components(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_base_url=url)


def test_attempt_latency_must_be_finite():
    with pytest.raises(ValidationError):
        RetrievalAttempt(action=Action.RETRIEVE_SPARSE, query="q", latency_ms=float("inf"))


def test_unexpected_dependency_failure_has_safe_service_result():
    class Broken:
        def extract(self, query, state=None):
            raise RuntimeError("SECRET C:/private")

    response = QueryService(feature_extractor=Broken()).execute_query(QueryRequest(query="q"))
    assert response.status == "failed"
    assert response.error == "workflow_failed"
    assert "SECRET" not in response.model_dump_json()


def test_terminal_direct_state_cannot_skip_citation_validation():
    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="r",
            original_query="What is x?",
            active_query="What is x?",
            status="completed",
            route=QueryRoute.DIRECT,
            answer="Invented.",
        )


def test_factual_terminal_cannot_claim_the_direct_exception():
    with pytest.raises(ValidationError):
        EvidenceOpsState(
            run_id="r",
            original_query="What is x?",
            active_query="What is x?",
            status="completed",
            route=QueryRoute.DIRECT,
            answer="Invented.",
            metadata={"require_citations": False, "citation_validation_failed": False},
        )


@pytest.mark.parametrize("kwargs", [{"base_url": ""}, {"model": ""}, {"timeout_seconds": 0}])
def test_explicit_invalid_ollama_options_are_not_replaced_by_defaults(kwargs):
    from evidenceops.generation.ollama import OllamaClient

    with pytest.raises(ValidationError):
        OllamaClient(**kwargs)


def test_generation_requires_evidence_evaluation():
    from evidenceops.evidence.adapter import adapt_retrieval_results
    from evidenceops.graph.nodes import generate_node
    from tests.integration.test_phase3_workflow import Generator
    from tests.unit.test_phase3_retrieval import result

    generator = Generator()
    state = EvidenceOpsState(
        run_id="r",
        original_query="q",
        active_query="q",
        next_action=Action.STOP,
        evidence=list(adapt_retrieval_results((result(),))),
    )
    updated = generate_node(state.to_langgraph_dict(), generator_client=generator)
    assert updated["abstention_reason"] == "evidence_below_threshold"
    assert generator.calls == 0


@pytest.mark.parametrize(
    "name",
    [
        "qdrant_timeout_seconds",
        "embedding_dimension",
        "rrf_k",
        "max_source_bytes",
        "simulated_cloud_input_cost_usd_per_1k",
        "simulated_cloud_output_cost_usd_per_1k",
    ],
)
def test_all_numeric_configuration_has_an_upper_bound(name):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: 10**30})


def test_route_merge_determinism_keeps_the_winning_route_score():
    from evidenceops.evidence.adapter import adapt_retrieval_results
    from tests.unit.test_evidence_adapter import _make_result

    dense = _make_result("same", "doc", 3, 0.9, "dense")
    sparse = _make_result("same", "doc", 1, 4.0, "sparse")
    forward = adapt_retrieval_results([dense, sparse])
    assert forward == adapt_retrieval_results([sparse, dense])
    assert forward[0].retrieval_method == "sparse"
    assert forward[0].retrieval_score == 4.0


def test_conflict_cannot_be_erased_by_reranker_selection():
    from evidenceops.graph.nodes import evaluate_evidence_node, rerank_node, retrieve_node
    from evidenceops.retrieval.reranker import reorder_rerank_results
    from tests.unit.test_phase3_retrieval import Retriever, result, state

    a, b = result("a"), result("b", 2)
    a = a.model_copy(
        update={"chunk": a.chunk.model_copy(update={"text": "The timeout is 30 seconds."})}
    )
    b = b.model_copy(
        update={"chunk": b.chunk.model_copy(update={"text": "The timeout is 60 seconds."})}
    )

    class DropContradiction:
        def rerank(self, query, candidates, limit):
            return reorder_rerank_results(candidates, (("a", 0.99), ("b", 0.01)), limit=1)

    retrieved = retrieve_node(state(), sparse_retriever=Retriever((a, b)))
    evaluated = evaluate_evidence_node(rerank_node(retrieved, reranker=DropContradiction()))
    assert evaluated["abstention_reason"] == "conflicting_evidence"
    assert evaluated["metadata"]["conflicting_pairs"] == [("a", "b")]


def test_response_metadata_does_not_expose_backend_payloads():
    from tests.integration.test_phase3_workflow import Generator
    from tests.unit.test_phase3_retrieval import Retriever, result

    candidate = result().model_copy(
        update={"metadata": {"source_uri": "docs/test.md", "hidden_payload": "SECRET"}}
    )
    response = QueryService(
        dense_retriever=Retriever((candidate,)), generator_client=Generator()
    ).execute_query(QueryRequest(query="documented parameter"))
    assert response.status == "completed"
    assert "SECRET" not in response.model_dump_json()


@pytest.mark.parametrize(
    "left,right",
    [
        ("count: int = 0", "version: int = 1"),
        ("```python\nfoo = 1\n```", "```python\nfoo = 3\n```"),
        ("The timeout is 30 seconds.", "The timeout is 30000 milliseconds."),
        ("Ollama streaming is supported.", "Other streaming is not supported."),
    ],
)
def test_examples_types_units_and_distinct_subjects_are_not_conflicts(left, right):
    from evidenceops.evidence.conflict import detect_evidence_conflicts
    from tests.unit.test_conflict import _make_evidence

    assert not detect_evidence_conflicts(
        [_make_evidence("a", left), _make_evidence("b", right)]
    ).has_conflict

import httpx
import pytest

from evidenceops.domain.errors import GenerationError
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.generation.ollama import OllamaClient
from evidenceops.graph.nodes import abstain_node, generate_node
from evidenceops.graph.service import QueryRequest, QueryService


class Generator:
    def generate(self, messages, temperature=0.0, max_tokens=None):
        return GenerationResponse(content="Hello!")


def test_factual_empty_context_never_generates():
    class Forbidden:
        def generate(self, *args, **kwargs):
            pytest.fail("factual question reached generator without evidence")

    state = EvidenceOpsState(
        run_id="r", original_query="What is a vector?", active_query="What is a vector?"
    ).to_langgraph_dict()
    updated = generate_node(state, generator_client=Forbidden())
    assert updated["abstention_reason"] == "evidence_below_threshold"


def test_greeting_propagates_citation_preference_and_completes():
    response = QueryService(generator_client=Generator()).execute_query(
        QueryRequest(query="Hello!", require_citations=False)
    )
    assert response.status == "completed"
    assert response.retrieval_calls == 0
    assert response.citations == []


def test_no_generator_is_unavailable():
    response = QueryService().execute_query(QueryRequest(query="Hello!", require_citations=False))
    assert response.abstention_reason == "generator_unavailable"


def test_abstention_discards_invalid_answer():
    state = EvidenceOpsState(
        run_id="r", original_query="q", active_query="q", answer="INVENTED [C99]", citations=["C99"]
    ).to_langgraph_dict()
    updated = abstain_node(state, "invalid_citations")
    assert "INVENTED" not in updated["answer"]
    assert updated["citations"] == []


@pytest.mark.parametrize(
    "status,body", [(500, "SECRET C:/private"), (200, "[]"), (200, "{bad json")]
)
def test_ollama_public_errors_are_sanitized(status, body):
    client = OllamaClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text=body))
    )
    with pytest.raises(GenerationError) as exc:
        client.generate([{"role": "user", "content": "hi"}])
    assert "SECRET" not in str(exc.value)
    assert "C:/private" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_ollama_remote_url_rejected():
    with pytest.raises(ValueError):
        OllamaClient(base_url="https://example.com/v1")


def test_ollama_completion_has_settings_driven_output_bound():
    import json

    def handler(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 256
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    client = OllamaClient(transport=httpx.MockTransport(handler))
    client.generate([{"role": "user", "content": "hello"}])

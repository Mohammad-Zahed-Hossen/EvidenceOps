import pytest

from evidenceops.domain.enums import QueryRoute
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.service import QueryRequest, QueryService
from tests.unit.test_phase3_retrieval import Retriever, result


class Generator:
    def __init__(self, answers=("A documented parameter [C1].",)):
        self.answers = answers
        self.calls = 0

    def generate(self, messages, temperature=0.0, max_tokens=None):
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return GenerationResponse(content=answer)


def test_citation_repair_succeeds_once():
    generator = Generator(("Parameter [C99].", "A documented parameter [C1]."))
    response = QueryService(
        dense_retriever=Retriever((result(),)), generator_client=generator
    ).execute_query(QueryRequest(query="documented parameter"))
    assert response.status == "completed"
    assert generator.calls == 2
    assert response.generation_attempts == 2


def test_repeated_reformulation_abstains_without_exception():
    class Repeated:
        def reformulate(self, query, previous_queries):
            return query

    response = QueryService(dense_retriever=Retriever(), reformulator=Repeated()).execute_query(
        QueryRequest(query="unsupported question")
    )
    assert response.abstention_reason == "duplicate_reformulation"
    assert response.retrieval_calls == 1


@pytest.mark.parametrize("calls", [1, 2, 3])
@pytest.mark.parametrize("iterations", [1, 2, 3])
def test_budgets_for_empty_retrieval(calls, iterations):
    retriever = Retriever()
    response = QueryService(dense_retriever=retriever).execute_query(
        QueryRequest(
            query="unsupported topic", max_retrieval_calls=calls, max_iterations=iterations
        )
    )
    assert response.status == "abstained"
    assert response.retrieval_calls == retriever.calls <= calls
    assert response.iterations <= iterations
    assert response.generation_attempts == 0


def test_fallback_then_success_records_both_routes():
    response = QueryService(
        dense_retriever=Retriever(fail=True),
        sparse_retriever=Retriever((result(),)),
        generator_client=Generator(),
    ).execute_query(QueryRequest(query="documented parameter"))
    assert response.status == "completed"
    assert response.retrieval_calls == 2
    assert [a.route for a in response.attempts] == [QueryRoute.DENSE, QueryRoute.SPARSE]


def test_persistent_conflict_abstains_and_preserves_ids():
    a, b = result("a"), result("b", 2)
    a = a.model_copy(
        update={"chunk": a.chunk.model_copy(update={"text": "The timeout is 30 seconds."})}
    )
    b = b.model_copy(
        update={"chunk": b.chunk.model_copy(update={"text": "The timeout is 60 seconds."})}
    )
    response = QueryService(dense_retriever=Retriever((a, b))).execute_query(
        QueryRequest(query="What is the timeout?")
    )
    assert response.abstention_reason == "conflicting_evidence"
    assert response.conflicting_pairs == [("a", "b")]


def test_settings_and_trace_propagate():
    from evidenceops.settings import Settings

    response = QueryService(
        generator_client=Generator(("Hello!",)),
        settings=Settings(_env_file=None, max_context_chars=1000),
    ).execute_query(QueryRequest(query="Hello!", require_citations=False, trace_id="trace-test"))
    assert response.trace_id == "trace-test"
    assert response.route == QueryRoute.DIRECT

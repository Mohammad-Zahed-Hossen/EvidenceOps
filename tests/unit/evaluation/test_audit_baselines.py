"""Production retrieval contracts and resource cleanup in benchmark baselines."""

import tracemalloc

import pytest

from evidenceops.evaluation.contracts import EvaluationSample
from evidenceops.evaluation.systems import BM25RAG, NaiveDenseRAG, TwoStepHybrid
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.retrieval.reranker import FlashRankReranker
from tests.unit.test_phase3_retrieval import Retriever, result


def sample():
    return EvaluationSample(
        id="q", question="documented parameter", type="single_fact", split="dev"
    )


class Generator:
    def __init__(self, answer="A documented parameter [C1]."):
        self.answer = answer
        self.messages = []

    def generate(self, messages, temperature=0.0, max_tokens=None):
        self.messages = messages
        return GenerationResponse(content=self.answer)


@pytest.mark.parametrize("kind", ["dense", "sparse"])
def test_baselines_deliver_real_chunk_text_to_generator(kind):
    generator = Generator()
    system = (
        NaiveDenseRAG(dense_retriever=Retriever((result(),)), generator_service=generator)
        if kind == "dense"
        else BM25RAG(sparse_retriever=Retriever((result(),)), generator_service=generator)
    )
    output = system.execute(sample())
    assert "A documented parameter." in str(generator.messages)
    assert "placeholder text" not in str(generator.messages)
    assert output.status == "completed"


def test_two_step_hybrid_accepts_real_flashrank_contract():
    class Backend:
        def rerank(self, request):
            return [{"id": p["id"], "score": 0.9} for p in request.passages]

    ranker = FlashRankReranker()
    ranker._ranker = Backend()
    retriever = Retriever((result(),))
    output = TwoStepHybrid(retriever, ranker, Generator()).execute(sample())
    assert retriever.calls == 2
    assert output.status == "completed"


def test_baseline_rejects_unknown_citations():
    output = BM25RAG(
        sparse_retriever=Retriever((result(),)), generator_service=Generator("Invented [C99].")
    ).execute(sample())
    assert output.status == "abstained"
    assert "Invented" not in output.generated_answer


def test_failed_execution_releases_memory_tracer():
    tracemalloc.stop()
    try:
        with pytest.raises(RuntimeError):
            BM25RAG(sparse_retriever=Retriever(fail=True)).execute(sample())
        assert not tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()


def test_factory_baseline_context_parity_and_lazy_learned_loading(monkeypatch):
    from evidenceops.evaluation import factory
    from evidenceops.settings import Settings

    monkeypatch.setattr(factory, "build_documentation_service", lambda _: object())
    monkeypatch.setattr(
        factory, "LearnedRetrievalController", lambda **_: pytest.fail("Unexpected model load")
    )
    settings = Settings(_env_file=None, top_k_context=2, max_context_chars=4000)
    systems = factory.build_benchmark_systems(
        settings, ["NaiveDenseRAG", "BM25RAG", "TwoStepHybrid"]
    )
    assert all(system.top_k == 2 for system in systems)
    assert all(system.max_context_chars == 4000 for system in systems)


def test_resource_unmeasured_values_are_null(monkeypatch):
    from evidenceops.evaluation import resources

    monkeypatch.setattr(resources.sys, "platform", "unsupported")
    monkeypatch.setattr(resources.os.path, "exists", lambda _: False)
    snapshot = resources.get_current_resource_snapshot()
    assert snapshot.cpu_percent is None
    assert snapshot.ram_total_mb is None


def test_api_and_benchmarks_never_acquire_models_during_requests(monkeypatch):
    from evidenceops.api.service import ApiService
    from evidenceops.evaluation import factory
    from evidenceops.settings import Settings

    observed = []

    def documents(settings):
        observed.append(settings.local_models_only)
        return object()

    monkeypatch.setattr(factory, "build_documentation_service", documents)
    monkeypatch.setattr("evidenceops.retrieval.service.build_documentation_service", documents)
    settings = Settings(_env_file=None, local_models_only=False)
    factory.build_benchmark_systems(settings, ["BM25RAG"])
    ApiService(settings).get_query_service()
    assert observed == [True, True]

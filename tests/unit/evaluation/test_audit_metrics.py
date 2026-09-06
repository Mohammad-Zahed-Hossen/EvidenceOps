"""Hand-calculated metric edge cases."""

import pytest

from evidenceops.evaluation.metrics import (
    calculate_abstention_accuracy,
    calculate_citation_metrics,
    calculate_ndcg_at_k,
)


def test_duplicate_relevant_chunks_do_not_inflate_ndcg():
    assert calculate_ndcg_at_k(["a", "a"], ["a"]) == pytest.approx(1.0)


def test_two_labels_for_one_chunk_do_not_inflate_citation_recall():
    metrics = calculate_citation_metrics(
        "Fact [C1] [C2].", ["C1", "C2"], {"C1": "a", "C2": "a"}, ["a"], ["a"]
    )
    assert metrics["citation_recall"] == 1.0


def test_unsupported_question_citation_recall_is_zero():
    assert (
        calculate_citation_metrics("Fact [C1].", ["C1"], {"C1": "a"}, [], ["a"])["citation_recall"]
        == 0.0
    )


def test_workflow_failure_is_not_correct_answerable_abstention_decision():
    assert calculate_abstention_accuracy("failed", False) == {
        "correct": False,
        "outcome": "execution_failed",
    }


def test_three_identical_pairs_do_not_produce_zero_p_value():
    from evidenceops.evaluation.statistics import compute_paired_bootstrap

    result = compute_paired_bootstrap([0, 0, 0], [1, 1, 1], "diagnostic")
    assert result.p_value == 0.25
    assert not result.statistically_significant


def test_bootstrap_resampling_is_bounded():
    from evidenceops.evaluation.statistics import compute_paired_bootstrap

    with pytest.raises(ValueError):
        compute_paired_bootstrap([0], [1], "diagnostic", n_resamples=10001)


def test_score_reports_unreviewed_facts_separately():
    from evidenceops.evaluation.contracts import AtomicFact
    from evidenceops.evaluation.scoring import evaluate_system_output
    from evidenceops.evaluation.systems import BM25RAG
    from tests.unit.evaluation.test_audit_baselines import Generator, sample
    from tests.unit.test_phase3_retrieval import Retriever, result

    question = sample().model_copy(
        update={"atomic_facts": [AtomicFact(id="f", statement="A documented parameter.")]}
    )
    output = BM25RAG(
        sparse_retriever=Retriever((result(),)), generator_service=Generator()
    ).execute(question)
    score = evaluate_system_output(question, output)
    assert getattr(score, "unreviewed_fact_count", None) == 1
    assert score.reviewed_atomic_fact_f1 is None
    assert score.fact_metric_kind == "lexical_overlap_proxy"


def test_runner_records_failed_system_without_losing_other_results(tmp_path):
    from evidenceops.evaluation.contracts import DatasetSplit
    from evidenceops.evaluation.runner import BenchmarkRunner
    from evidenceops.evaluation.systems import BM25RAG
    from tests.unit.evaluation.test_audit_baselines import sample
    from tests.unit.test_phase3_retrieval import Retriever

    run = BenchmarkRunner(tmp_path).run_benchmark(
        "test", DatasetSplit.DEV, [sample()], [BM25RAG(sparse_retriever=Retriever(fail=True))]
    )
    assert run.manifest.sample_scores[0].abstention_outcome == "execution_failed"
    assert run.system_reports[0].failed_count == 1


def test_controller_macro_f1_includes_predicted_only_classes():
    from evidenceops.domain.enums import Action
    from evidenceops.evaluation.controller_benchmark import compute_controller_diagnostics

    report = compute_controller_diagnostics(
        [Action.STOP, Action.ABSTAIN], [Action.STOP, Action.STOP], "test"
    )
    assert report.macro_f1 == pytest.approx(1 / 3)


def test_risk_coverage_and_complete_support_have_explicit_denominators():
    from evidenceops.evaluation.contracts import GoldCitation
    from evidenceops.evaluation.scoring import aggregate_evaluation_scores, evaluate_system_output
    from evidenceops.evaluation.systems import SystemExecutionResult
    from tests.unit.evaluation.test_audit_baselines import sample

    answerable = sample().model_copy(
        update={
            "gold_chunk_ids": ["a", "b"],
            "gold_citations": [
                GoldCitation(doc_id="d1", chunk_id="a"),
                GoldCitation(doc_id="d2", chunk_id="b"),
            ],
        }
    )
    unsupported = sample().model_copy(update={"id": "u", "requires_abstention": True})
    output = SystemExecutionResult(
        run_id="r",
        sample_id="q",
        system_name="s",
        generated_answer="Answer",
        status="completed",
        retrieved_chunk_ids=["a", "b"],
        latency_ms=10,
    )
    first = evaluate_system_output(answerable, output)
    second = evaluate_system_output(unsupported, output)
    third = evaluate_system_output(answerable, output.model_copy(update={"status": "abstained"}))
    report = aggregate_evaluation_scores([first, second, third], "s")
    assert first.recall_at_10 == 1
    assert first.complete_support is True
    assert second.complete_support is None
    assert report.multi_source_complete_support_rate == 1
    assert report.answer_coverage == pytest.approx(2 / 3)
    assert report.false_abstention_rate == 0.5
    assert report.unsupported_answer_rate == 1
    assert report.reviewed_selective_risk is None


def test_manifest_preserves_sample_identity_and_statistics(tmp_path):
    from evidenceops.evaluation.contracts import DatasetSplit
    from evidenceops.evaluation.runner import BenchmarkRunner
    from evidenceops.evaluation.systems import BM25RAG
    from tests.unit.evaluation.test_audit_baselines import sample
    from tests.unit.test_phase3_retrieval import Retriever

    run = BenchmarkRunner(tmp_path).run_benchmark(
        "test", DatasetSplit.DEV, [sample()], [BM25RAG(sparse_retriever=Retriever(fail=True))]
    )
    assert len(run.manifest.input_identity["sample_sha256"]) == 64
    assert run.manifest.input_identity["sample_ids"] == ["q"]
    assert run.manifest.bootstrap_results == run.bootstrap_results

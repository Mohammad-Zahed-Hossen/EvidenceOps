"""Unit tests for deterministic evaluation metrics."""

from __future__ import annotations

import pytest

from evidenceops.domain.enums import RunStatus
from evidenceops.evaluation.contracts import AtomicFact
from evidenceops.evaluation.metrics import (
    calculate_abstention_accuracy,
    calculate_atomic_fact_f1,
    calculate_citation_metrics,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
)


def test_calculate_recall_at_k() -> None:
    gold = ["c1", "c2"]
    # Top 1 has c1 -> 1/2 = 0.5
    assert calculate_recall_at_k(["c1", "other"], gold, k=1) == pytest.approx(0.5)
    # Top 2 has both -> 2/2 = 1.0
    assert calculate_recall_at_k(["c1", "c2"], gold, k=2) == pytest.approx(1.0)
    # None found
    assert calculate_recall_at_k(["o1", "o2"], gold, k=2) == pytest.approx(0.0)
    # Empty gold
    assert calculate_recall_at_k(["c1"], [], k=5) == pytest.approx(0.0)


def test_calculate_reciprocal_rank() -> None:
    gold = ["c1"]
    # First position -> 1/1 = 1.0
    assert calculate_reciprocal_rank(["c1", "c2"], gold, max_k=10) == pytest.approx(1.0)
    # Third position -> 1/3 = 0.3333
    assert calculate_reciprocal_rank(["o1", "o2", "c1"], gold, max_k=10) == pytest.approx(1.0 / 3.0)
    # Beyond max_k -> 0.0
    assert calculate_reciprocal_rank(["o"] * 10 + ["c1"], gold, max_k=10) == pytest.approx(0.0)
    # Empty gold
    assert calculate_reciprocal_rank(["c1"], [], max_k=10) == pytest.approx(0.0)


def test_calculate_ndcg_at_k() -> None:
    gold = ["c1", "c2"]
    # Ideal order: c1 at 1, c2 at 2 -> nDCG = 1.0
    assert calculate_ndcg_at_k(["c1", "c2", "o1"], gold, k=3) == pytest.approx(1.0)
    # One hit at rank 1, second missing -> DCG = 1.0; IDCG = 1.6309
    score = calculate_ndcg_at_k(["c1", "o1", "o2"], gold, k=3)
    assert 0.60 < score < 0.62
    # Zero hits -> 0.0
    assert calculate_ndcg_at_k(["o1", "o2"], gold, k=3) == pytest.approx(0.0)
    # Empty gold -> 0.0
    assert calculate_ndcg_at_k(["c1"], [], k=3) == pytest.approx(0.0)


def test_calculate_atomic_fact_f1() -> None:
    facts = [
        AtomicFact(id="f1", statement="FastAPI uses status_code parameter."),
        AtomicFact(id="f2", statement="status.HTTP_201_CREATED can be passed."),
    ]
    # Full coverage in answer
    ans_full = (
        "The status_code parameter in FastAPI is used, and "
        "status.HTTP_201_CREATED can be passed [C1]."
    )
    m_full = calculate_atomic_fact_f1(ans_full, facts)
    assert m_full["precision"] == pytest.approx(1.0)
    assert m_full["recall"] == pytest.approx(1.0)
    assert m_full["f1"] == pytest.approx(1.0)

    # Partial coverage
    ans_part = "Only the status_code parameter is mentioned here."
    m_part = calculate_atomic_fact_f1(ans_part, facts)
    assert m_part["recall"] == pytest.approx(0.5)
    assert m_part["f1"] < 1.0

    # No facts defined
    m_empty = calculate_atomic_fact_f1("Any answer", [])
    assert m_empty["f1"] == pytest.approx(0.0)


def test_calculate_citation_metrics() -> None:
    # Gold chunk ids: c1, c2
    # Retrieved chunk ids: c1, c2, c3
    # Answer cites [C1] and [C2]
    ans = "FastAPI uses status_code [C1] and status constants [C2]."
    citations = ["C1", "C2"]
    # Mapping C1 -> c1, C2 -> c2
    chunk_mapping = {"C1": "c1", "C2": "c2"}

    metrics = calculate_citation_metrics(
        generated_answer=ans,
        citations=citations,
        citation_to_chunk=chunk_mapping,
        gold_chunk_ids=["c1", "c2"],
        retrieved_chunk_ids=["c1", "c2", "c3"],
    )
    assert metrics["citation_validity_rate"] == pytest.approx(1.0)
    assert metrics["citation_precision"] == pytest.approx(1.0)
    assert metrics["citation_recall"] == pytest.approx(1.0)

    # Hallucinated citation [C9] not in mapping or retrieved
    ans_bad = "FastAPI does this [C9]."
    metrics_bad = calculate_citation_metrics(
        generated_answer=ans_bad,
        citations=["C9"],
        citation_to_chunk={},
        gold_chunk_ids=["c1"],
        retrieved_chunk_ids=["c1"],
    )
    assert metrics_bad["citation_validity_rate"] == pytest.approx(0.0)
    assert metrics_bad["citation_precision"] == pytest.approx(0.0)


def test_calculate_abstention_accuracy() -> None:
    # Expected abstention and abstained -> True positive
    res_tp = calculate_abstention_accuracy(
        generated_status=RunStatus.ABSTAINED,
        requires_abstention=True,
    )
    assert res_tp["correct"] is True
    assert res_tp["outcome"] == "true_positive"

    # Expected answerable, but abstained -> False positive
    res_fp = calculate_abstention_accuracy(
        generated_status=RunStatus.ABSTAINED,
        requires_abstention=False,
    )
    assert res_fp["correct"] is False
    assert res_fp["outcome"] == "false_positive"

    # Expected abstention, but answered -> False negative
    res_fn = calculate_abstention_accuracy(
        generated_status=RunStatus.COMPLETED,
        requires_abstention=True,
    )
    assert res_fn["correct"] is False
    assert res_fn["outcome"] == "false_negative"

    # Expected answerable, and completed -> True negative
    res_tn = calculate_abstention_accuracy(
        generated_status=RunStatus.COMPLETED,
        requires_abstention=False,
    )
    assert res_tn["correct"] is True
    assert res_tn["outcome"] == "true_negative"

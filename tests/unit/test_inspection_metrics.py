"""Unit tests for diagnostic retrieval inspection metrics rules."""

from __future__ import annotations


def calculate_recall_at_k(retrieved_cids: list[str], gold_cids: set[str], k: int) -> float:
    if not gold_cids:
        return 0.0
    return len(set(retrieved_cids[:k]) & gold_cids) / len(gold_cids)


def calculate_reciprocal_rank(
    retrieved_cids: list[str], gold_cids: set[str], max_k: int = 10
) -> float:
    if not gold_cids:
        return 0.0
    for rank, cid in enumerate(retrieved_cids[:max_k], start=1):
        if cid in gold_cids:
            return 1.0 / rank
    return 0.0


def calculate_multi_source_metrics(
    retrieved_cids: list[str], required_cids: set[str], k: int = 5
) -> dict[str, bool | float]:
    retrieved_set = set(retrieved_cids[:k])
    intersection = retrieved_set & required_cids
    any_hit = len(intersection) > 0
    complete_hit = len(intersection) == len(required_cids)
    recall = len(intersection) / len(required_cids) if required_cids else 0.0
    return {
        "any_support_hit": any_hit,
        "complete_support_hit": complete_hit,
        "fractional_recall": recall,
    }


def test_recall_at_k_single_source() -> None:
    gold = {"chunk_1"}
    assert calculate_recall_at_k(["chunk_1", "chunk_2"], gold, k=1) == 1.0
    assert calculate_recall_at_k(["chunk_2", "chunk_1"], gold, k=1) == 0.0
    assert calculate_recall_at_k(["chunk_2", "chunk_1"], gold, k=5) == 1.0


def test_recall_at_k_multi_source_partial_and_complete() -> None:
    gold = {"chunk_1", "chunk_2"}
    # Only 1 retrieved in top 1 -> recall 0.5
    assert calculate_recall_at_k(["chunk_1", "other"], gold, k=1) == 0.5
    # Both retrieved in top 2 -> recall 1.0
    assert calculate_recall_at_k(["chunk_1", "chunk_2"], gold, k=2) == 1.0
    # None retrieved -> recall 0.0
    assert calculate_recall_at_k(["other_1", "other_2"], gold, k=2) == 0.0


def test_empty_gold_set_returns_zero_recall() -> None:
    assert calculate_recall_at_k(["chunk_1"], set(), k=5) == 0.0
    assert calculate_reciprocal_rank(["chunk_1"], set(), max_k=10) == 0.0


def test_reciprocal_rank_uses_first_relevant_chunk() -> None:
    gold = {"chunk_2", "chunk_4"}
    # chunk_2 appears at rank 2 -> RR is 0.5
    assert calculate_reciprocal_rank(["chunk_1", "chunk_2", "chunk_3", "chunk_4"], gold) == 0.5
    # Beyond max_k (10) -> 0.0
    cids = ["other"] * 10 + ["chunk_2"]
    assert calculate_reciprocal_rank(cids, gold, max_k=10) == 0.0


def test_multi_source_metrics_distinguishes_any_and_complete_hit() -> None:
    required = {"chunk_doc_a", "chunk_doc_b"}
    # Only doc A present
    res_partial = calculate_multi_source_metrics(["chunk_doc_a", "other"], required, k=5)
    assert res_partial["any_support_hit"] is True
    assert res_partial["complete_support_hit"] is False
    assert res_partial["fractional_recall"] == 0.5

    # Both present
    res_complete = calculate_multi_source_metrics(["chunk_doc_a", "chunk_doc_b"], required, k=5)
    assert res_complete["any_support_hit"] is True
    assert res_complete["complete_support_hit"] is True
    assert res_complete["fractional_recall"] == 1.0

"""Deterministic evaluation metrics for retrieval, generation, citation, and abstention."""

from __future__ import annotations

import math
import re
from typing import Any

from evidenceops.domain.enums import RunStatus
from evidenceops.evaluation.contracts import AtomicFact


def calculate_recall_at_k(
    retrieved_chunk_ids: list[str], gold_chunk_ids: list[str], k: int
) -> float:
    """Calculate Recall@K: proportion of gold chunks retrieved in top k."""
    if not gold_chunk_ids:
        return 0.0
    gold_set = set(gold_chunk_ids)
    top_k_set = set(retrieved_chunk_ids[:k])
    return len(top_k_set & gold_set) / len(gold_set)


def calculate_reciprocal_rank(
    retrieved_chunk_ids: list[str], gold_chunk_ids: list[str], max_k: int = 10
) -> float:
    """Calculate Mean Reciprocal Rank (MRR) up to max_k."""
    if not gold_chunk_ids:
        return 0.0
    gold_set = set(gold_chunk_ids)
    for rank, cid in enumerate(retrieved_chunk_ids[:max_k], start=1):
        if cid in gold_set:
            return 1.0 / rank
    return 0.0


def calculate_ndcg_at_k(
    retrieved_chunk_ids: list[str], gold_chunk_ids: list[str], k: int = 10
) -> float:
    """Calculate Normalized Discounted Cumulative Gain (nDCG@K) with binary relevance."""
    if not gold_chunk_ids:
        return 0.0
    gold_set = set(gold_chunk_ids)

    # DCG
    dcg = 0.0
    seen: set[str] = set()
    for rank, cid in enumerate(retrieved_chunk_ids[:k], start=1):
        rel = 1.0 if cid in gold_set and cid not in seen else 0.0
        seen.add(cid)
        dcg += rel / math.log2(rank + 1)

    # IDCG (ideal ranking where all gold items appear first)
    ideal_hits = min(len(gold_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

    if idcg <= 0.0:
        return 0.0
    return dcg / idcg


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercased alphanumeric tokens."""
    return set(re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower()))


def calculate_atomic_fact_f1(
    generated_answer: str, atomic_facts: list[AtomicFact]
) -> dict[str, float]:
    """Legacy lexical-overlap proxy; NOT factual precision, recall, or F1.

    A lexical match is counted if its salient non-stopword tokens
    are substantially present in the generated answer.
    """
    if not atomic_facts:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "matched_facts": 0.0}

    stop_words = {
        "a",
        "an",
        "the",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "as",
        "with",
        "that",
        "this",
        "it",
        "from",
        "can",
        "uses",
        "use",
        "used",
        "has",
        "have",
        "sets",
        "set",
        "also",
        "into",
    }

    ans_tokens = _tokenize(generated_answer)
    if not ans_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "matched_facts": 0.0}

    matched_facts = 0
    for fact in atomic_facts:
        fact_tokens = _tokenize(fact.statement) - stop_words
        if not fact_tokens:
            continue
        # If at least 50% of salient fact tokens match answer
        overlap = len(fact_tokens & ans_tokens)
        match_ratio = overlap / len(fact_tokens)
        if match_ratio >= 0.50:
            matched_facts += 1

    recall = matched_facts / len(atomic_facts)
    # Precision: proportion of matched facts over estimated generated claims
    # (heuristically, generated sentences or 1 claim per matched fact + ungrounded text ratio)
    precision = 1.0 if matched_facts > 0 else 0.0
    if recall > 0 and len(generated_answer.strip()) > 0:
        # Penalize if answer is excessively long with few matched facts
        precision = min(1.0, (matched_facts * 150) / max(len(generated_answer), 1))
        # ensure precision is at least reasonable if all facts matched
        if recall == 1.0 and precision < 0.5:
            precision = 0.5
        elif recall == 1.0:
            precision = 1.0

    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched_facts": float(matched_facts),
    }


def calculate_citation_metrics(
    generated_answer: str,
    citations: list[str],
    citation_to_chunk: dict[str, str],
    gold_chunk_ids: list[str],
    retrieved_chunk_ids: list[str],
) -> dict[str, float | bool]:
    """Calculate citation validity, citation precision, and citation recall."""
    # Find all citation markers in the answer like [C1], [C2]
    inline_markers = set(re.findall(r"\[C(\d+)\]", generated_answer))
    found_citations = {f"C{num}" for num in inline_markers} | set(citations)

    if not found_citations:
        # If no citations were present
        return {
            "citation_validity_rate": 0.0,
            "citation_precision": 0.0,
            "citation_recall": 0.0,
            "all_citations_valid": False,
        }

    retrieved_set = set(retrieved_chunk_ids)
    gold_set = set(gold_chunk_ids)

    valid_cites = 0
    grounded_gold_cites = 0
    cited_gold_chunks: set[str] = set()
    for cite in found_citations:
        chunk_id = citation_to_chunk.get(cite)
        if chunk_id and chunk_id in retrieved_set:
            valid_cites += 1
            if chunk_id in gold_set:
                grounded_gold_cites += 1
                cited_gold_chunks.add(chunk_id)

    validity_rate = valid_cites / len(found_citations)
    precision = grounded_gold_cites / len(found_citations) if found_citations else 0.0
    recall = len(cited_gold_chunks) / len(gold_set) if gold_set else 0.0

    return {
        "citation_validity_rate": validity_rate,
        "citation_precision": precision,
        "citation_recall": recall,
        "all_citations_valid": validity_rate == 1.0,
    }


def calculate_abstention_accuracy(
    generated_status: RunStatus,
    requires_abstention: bool,
) -> dict[str, Any]:
    """Evaluate whether system correctly abstained when unanswerable or proceeded."""
    if generated_status not in {RunStatus.COMPLETED, RunStatus.ABSTAINED}:
        return {"correct": False, "outcome": "execution_failed"}
    is_abstained = generated_status == RunStatus.ABSTAINED

    if requires_abstention and is_abstained:
        return {"correct": True, "outcome": "true_positive"}
    elif not requires_abstention and not is_abstained:
        return {"correct": True, "outcome": "true_negative"}
    elif not requires_abstention and is_abstained:
        return {"correct": False, "outcome": "false_positive"}
    else:  # requires_abstention and not is_abstained
        return {"correct": False, "outcome": "false_negative"}

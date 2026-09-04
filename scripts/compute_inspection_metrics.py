"""Analyze 30-question diagnostic retrieval inspection results and compute comprehensive metrics."""

from __future__ import annotations

import json
from pathlib import Path


def compute_metrics() -> dict:
    repo_root = Path(__file__).resolve().parent.parent
    run_file = repo_root / "data" / "eval" / "retrieval_inspection_run.json"
    judgments_dir = repo_root / "eval" / "judgments"
    judgments_dir.mkdir(parents=True, exist_ok=True)
    judgments_path = judgments_dir / "phase1c_retrieval_judgments.json"

    data = json.loads(run_file.read_text(encoding="utf-8"))
    questions = data["questions"]

    methods = ["sparse", "dense", "hybrid", "reranked"]
    answerable_q = [q for q in questions if q["answerable"]]
    unanswerable_q = [q for q in questions if not q["answerable"]]
    total_ans = len(answerable_q)  # 27
    total_unans = len(unanswerable_q)  # 3

    metrics_by_method = {}

    for method in methods:
        res_key = f"{method}_results"
        r1_sum = 0.0
        r5_sum = 0.0
        r10_sum = 0.0
        rr_sum = 0.0

        for q in answerable_q:
            gold_cids = set(q["gold_supporting_chunk_ids"])
            if not gold_cids:
                continue
            results = q[res_key]
            cids = [r["chunk_id"] for r in results]

            # In reranked mode, only top 6 are retained
            eval_limit_10 = min(10, len(cids))

            # Full multi-chunk recall: |Rel ∩ Retrieved@K| / |Rel|
            rel_count = len(gold_cids)
            r1_hits = len(set(cids[:1]) & gold_cids)
            r5_hits = len(set(cids[:5]) & gold_cids)
            r10_hits = len(set(cids[:eval_limit_10]) & gold_cids)

            r1_sum += r1_hits / rel_count
            r5_sum += r5_hits / rel_count
            r10_sum += r10_hits / rel_count

            # Reciprocal rank (first matching gold chunk)
            first_rank = 0
            for rank_idx, cid in enumerate(cids[:10], start=1):
                if cid in gold_cids:
                    first_rank = rank_idx
                    break
            if first_rank > 0:
                rr_sum += 1.0 / first_rank

        m_recall_1 = r1_sum / total_ans
        m_recall_5 = r5_sum / total_ans
        m_recall_10 = r1_sum if False else (r10_sum / total_ans)
        m_mrr = rr_sum / total_ans

        metrics_by_method[method] = {
            "recall@1": {
                "score": round(m_recall_1, 4),
                "display": f"{r1_sum:.2f} / {total_ans} ({m_recall_1 * 100:.2f}%)",
            },
            "recall@5": {
                "score": round(m_recall_5, 4),
                "display": f"{r5_sum:.2f} / {total_ans} ({m_recall_5 * 100:.2f}%)",
            },
            "recall@10": {
                "score": round(m_recall_10, 4),
                "display": f"{r10_sum:.2f} / {total_ans} ({m_recall_10 * 100:.2f}%)",
                "note": (
                    "Reranked evaluated on 6 retained candidates" if method == "reranked" else None
                ),
            },
            "mrr@10": {
                "score": round(m_mrr, 4),
                "display": f"{rr_sum:.2f} / {total_ans} (MRR: {m_mrr:.4f})",
            },
        }

    # Multi-source questions analysis (q022, q023, q024, q025)
    multi_source_q = [q for q in questions if q["category"] == "cross_document_comparison"]
    multi_source_report = {}
    for method in methods:
        res_key = f"{method}_results"
        any_hit_5 = 0
        complete_hit_5 = 0
        total_rel_retrieved_5 = 0.0
        total_required_chunks = 0

        for q in multi_source_q:
            gold_cids = set(q["gold_supporting_chunk_ids"])
            total_required_chunks += len(gold_cids)
            cids = [r["chunk_id"] for r in q[res_key][:5]]
            intersection = set(cids) & gold_cids
            if len(intersection) > 0:
                any_hit_5 += 1
            if len(intersection) == len(gold_cids):
                complete_hit_5 += 1
            total_rel_retrieved_5 += len(intersection)

        n_ms = len(multi_source_q)
        pct_any = any_hit_5 / n_ms * 100
        pct_comp = complete_hit_5 / n_ms * 100
        pct_rec = total_rel_retrieved_5 / total_required_chunks * 100
        multi_source_report[method] = {
            "any_support_hit@5": f"{any_hit_5} / {n_ms} ({pct_any:.1f}%)",
            "complete_support_hit@5": f"{complete_hit_5} / {n_ms} ({pct_comp:.1f}%)",
            "recall@5_over_all_required": (
                f"{total_rel_retrieved_5:.1f} / {total_required_chunks} ({pct_rec:.1f}%)"
            ),
        }

    # Unanswerable query behavior
    unanswerable_report = {
        "total_unanswerable_questions": total_unans,
        "abstention_rate_phase_1c": f"0 / {total_unans} (0.0%)",
        "diagnostic_status": "unanswerable_incorrectly_retrieved",
        "explanation": (
            "The Phase 1C retrieval layer always returns nearest candidates when available. "
            "These results show that retrieval alone does not detect unsupported questions. "
            "Abstention and evidence-sufficiency decisions belong to later phases, so this is "
            "a diagnostic limitation rather than proof of a Phase 1C implementation defect."
        ),
    }

    # Provenance stability
    total_evaluated = sum(len(q[f"{m}_results"]) for q in questions for m in methods)
    stable_provenance = sum(
        1
        for q in questions
        for m in methods
        for r in q[f"{m}_results"]
        if r.get("chunk_id") and r.get("document_id") and r.get("heading_path") is not None
    )

    # Human judgments record (pending human review)
    judgments_record = []
    diagnostic_counts = {}
    for q in questions:
        diag = q["automatic_diagnostic"]
        diagnostic_counts[diag] = diagnostic_counts.get(diag, 0) + 1
        judgments_record.append(
            {
                "question_id": q["question_id"],
                "query": q["query"],
                "category": q["category"],
                "answerable": q["answerable"],
                "automatic_diagnostic": diag,
                "human_judgment": "pending_human_review",
                "reviewer_notes": "",
                "diagnostic_note": q["diagnostic_note"],
                "top_reranked_chunk_id": (
                    q["reranked_results"][0]["chunk_id"] if q["reranked_results"] else None
                ),
                "top_reranked_title": (
                    q["reranked_results"][0]["title"] if q["reranked_results"] else None
                ),
            }
        )

    judgments_path.write_text(
        json.dumps(
            {
                "inspection_set_id": "phase1c-retrieval-30",
                "status": "pending_human_review",
                "judgments_pending_count": len(questions),
                "judgments": judgments_record,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "metrics_by_method": metrics_by_method,
        "multi_source_metrics": multi_source_report,
        "unanswerable_query_behavior": unanswerable_report,
        "provenance_stability": {
            "total_evaluated_chunks": total_evaluated,
            "stable_provenance_count": stable_provenance,
            "provenance_percentage": round(stable_provenance / total_evaluated * 100, 2),
        },
        "automatic_diagnostic_summary": diagnostic_counts,
        "human_judgment_gate_status": "pending_human_review (30 awaiting human review)",
    }

    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    compute_metrics()

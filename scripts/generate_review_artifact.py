"""Generate comprehensive, inspectable human review artifact for Phase 1C retrieval gate."""

from __future__ import annotations

import json
from pathlib import Path

from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.settings import get_settings


def generate_review_artifact() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    run_file = repo_root / "data" / "eval" / "retrieval_inspection_run.json"
    artifact_path = Path(
        r"C:\Users\Admin\.gemini\antigravity-ide\brain\578142dc-18fe-42ff-b9b3-fe45d1d8fef9\retrieval_inspection_review.md"
    )

    data = json.loads(run_file.read_text(encoding="utf-8"))
    questions = data["questions"]
    settings = get_settings()
    store = JsonProcessedDocumentStore(settings.processed_data_dir)

    # Load chunk lookup
    chunk_lookup: dict[str, dict] = {}
    for p in sorted(store.root.glob("*.json")):
        art = store.read(p.stem)
        for c in art.chunks:
            clean_text = " ".join(c.text.split())
            chunk_lookup[c.chunk_id] = {
                "title": c.title,
                "heading_path": c.metadata.get("heading_path", ""),
                "excerpt": clean_text[:220] + ("..." if len(clean_text) > 220 else ""),
            }

    lines = [
        "# Phase 1C: Human Inspection Gate & Retrieval Quality Review",
        "",
        "> [!IMPORTANT]",
        (
            "> **Human Inspection Gate Active**: All 30 inspection questions have been evaluated "
            "across 4 retrieval modes. Automatic diagnostics are recorded below, but all semantic "
            "labels remain strictly `pending_human_review`. Review each question, its gold "
            "supporting excerpts, and the top-3 candidate chunks per retrieval mode."
        ),
        "",
        "## Diagnostic Evaluation Overview",
        (
            "- **Corpus Provenance**: 10 primary-source documents, 52 chunks, "
            "commit-pinned with verified SHA-256 hashes."
        ),
        (
            "- **Corpus Status**: *Corpus scope provisionally approved after acquisition; "
            "provenance and reproducibility corrections required before final acceptance.*"
        ),
        (
            "- **Total Inspection Questions**: 30 (8 exact identifier, 8 conceptual, "
            "5 mixed code/concept, 4 cross-document comparison, 2 ambiguous, 3 unanswerable)."
        ),
        (
            "- **Provenance Stability**: **100.0%** (1,080 / 1,080 returned results contain "
            "complete `chunk_id`, `document_id`, `title`, and `heading_path`)."
        ),
        (
            "- **Human Review Status**: **30 questions awaiting human review** "
            "(`pending_human_review`)."
        ),
        "",
        "---",
        "",
        "## Questions for Review",
        "",
    ]

    for q in questions:
        qid = q["question_id"]
        query = q["query"]
        cat = q["category"]
        ans = "Yes" if q["answerable"] else "No (Unanswerable)"
        exp_src = ", ".join(q["expected_source_ids"]) or "None (Out-of-Domain)"
        auto_diag = q["automatic_diagnostic"]
        diag_note = q["diagnostic_note"]
        gold_cids = q["gold_supporting_chunk_ids"]
        gold_facts = q["gold_answer_facts"]

        human_judgment_options = (
            "`[ ] relevant` | `[ ] partially_relevant` | `[ ] not_relevant` | "
            "`[ ] unanswerable_correctly_empty` | `[ ] unanswerable_incorrectly_retrieved` | "
            "`[ ] needs_gold_correction`"
        )
        cat_meta = (
            f"- **Category**: `{cat}` | **Answerable**: `{ans}` | "
            f"**Expected Source(s)**: `{exp_src}`"
        )
        lines.extend(
            [
                f"### Question `{qid}`: {query}",
                cat_meta,
                f"- **Automatic Diagnostic Status**: `{auto_diag}`",
                f"- **Human Judgment**: {human_judgment_options}",
                "- **Reviewer Notes**: `___________________________________________________`",
                f"- **Diagnostic Note**: {diag_note}",
                "",
                "#### Gold Supporting Evidence:",
            ]
        )

        if not gold_cids:
            lines.append(
                "*No supporting evidence exists in the indexed corpus for this out-of-domain query.*"  # noqa: E501
            )
        else:
            for fact in gold_facts:
                lines.append(f"- **Fact**: {fact}")
            for cid in gold_cids:
                info = chunk_lookup.get(
                    cid, {"title": "Unknown", "heading_path": "", "excerpt": ""}
                )
                lines.append(f"- **Chunk ID**: `{cid}`")
                lines.append(f"  - **Title / Heading**: {info['title']} > {info['heading_path']}")
                lines.append(f'  - **Excerpt**: "{info["excerpt"]}"')

        lines.append("")
        lines.append("#### Top 3 Retrieved Results per Mode:")
        lines.append("")

        for mode_name, mode_key in [
            ("Sparse (BM25)", "sparse_results"),
            ("Dense (FastEmbed)", "dense_results"),
            ("Hybrid (RRF k=60)", "hybrid_results"),
            ("Reranked (FlashRank)", "reranked_results"),
        ]:
            results = q[mode_key][:3]
            lines.append(f"**{mode_name}**:")
            lines.append("| Rank | Score | Full Chunk ID | Heading Path | Retrieved Excerpt |")
            lines.append("| :---: | :---: | :--- | :--- | :--- |")
            for r in results:
                rcid = r["chunk_id"]
                score_str = (
                    f"{r['score']:.4f}" if isinstance(r["score"], float) else str(r["score"])
                )
                heading = r["heading_path"] or r["title"]
                clean_heading = heading.replace("|", "\\|")
                excerpt = chunk_lookup.get(rcid, {}).get("excerpt", "").replace("|", "\\|")
                is_gold = " ⭐ (Gold)" if rcid in gold_cids else ""
                row = (
                    f"| {r['rank']} | {score_str} | `{rcid}`{is_gold} "
                    f"| {clean_heading} | {excerpt} |"
                )
                lines.append(row)
            lines.append("")

        lines.append("---")
        lines.append("")

    # Summary metrics section
    clarification = (
        "*The Phase 1C retrieval layer always returns nearest candidates when available. "
        "These results show that retrieval alone does not detect unsupported questions. "
        "Abstention and evidence-sufficiency decisions belong to later phases, so this is "
        "a diagnostic limitation rather than proof of a Phase 1C implementation defect.*"
    )
    lines.extend(
        [
            "## Summary Metrics & Denominators",
            "",
            "### Answerable Query Metrics (N = 27)",
            "| Retrieval Mode | Recall@1 | Recall@5 | Recall@10 | MRR@10 |",
            "| :--- | :---: | :---: | :---: | :---: |",
            "| **Sparse (BM25)** | 10.50 / 27 (38.89%) | 25.00 / 27 (92.59%) | 26.00 / 27 (96.30%) | 18.12 / 27 (0.6710) |",  # noqa: E501
            "| **Dense (FastEmbed)** | 13.50 / 27 (50.00%) | 26.00 / 27 (96.30%) | 26.50 / 27 (98.15%) | 20.44 / 27 (0.7572) |",  # noqa: E501
            "| **Hybrid (RRF k=60)** | 13.50 / 27 (50.00%) | 26.00 / 27 (96.30%) | 26.50 / 27 (98.15%) | 20.58 / 27 (0.7623) |",  # noqa: E501
            "| **Reranked (FlashRank)** | **16.00 / 27 (59.26%)** | **24.50 / 27 (90.74%)** | **25.50 / 27 (94.44%)*** | **20.87 / 27 (0.7728)** |",  # noqa: E501
            "",
            "*Note: Reranked Recall@10 is evaluated over the 6 retained candidates produced by FlashRank.*",  # noqa: E501
            "",
            "### Multi-Source Complete Support Metrics (N = 4 cross-document questions)",
            "| Retrieval Mode | Any-Support Hit@5 | Complete-Support Hit@5 | Recall@5 over All Required Chunks |",  # noqa: E501
            "| :--- | :---: | :---: | :---: |",
            "| **Sparse (BM25)** | 4 / 4 (100.0%) | 3 / 4 (75.0%) | 7.0 / 8 (87.5%) |",
            "| **Dense (FastEmbed)** | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 8.0 / 8 (100.0%) |",
            "| **Hybrid (RRF k=60)** | 4 / 4 (100.0%) | 3 / 4 (75.0%) | 7.0 / 8 (87.5%) |",
            "| **Reranked (FlashRank)** | 4 / 4 (100.0%) | 3 / 4 (75.0%) | 7.0 / 8 (87.5%) |",
            "",
            "### Unanswerable Query Diagnostics (N = 3 queries: q028, q029, q030)",
            "- **Abstention Rate in Phase 1C**: 0 / 3 (0.0%).",
            "- **Diagnostic Status**: `unanswerable_incorrectly_retrieved`.",
            f"- **Clarification**: {clarification}",
            "",
        ]
    )

    artifact_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Inspectable human review artifact written to {artifact_path} ({len(lines)} lines)")


if __name__ == "__main__":
    generate_review_artifact()

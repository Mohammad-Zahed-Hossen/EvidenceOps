# LiteBridge Frozen Evaluation Corpus (v1.0.0)

This directory contains the frozen, deterministic evaluation dataset and fixtures for **LiteBridge Phase L8: Reproducible Evaluation and Optional Learned-Controller Experiment**.

## Overview

The evaluation suite tests LiteBridge's retrieval planning, context preparation, extractive compression, abstention, citation integrity, latency, and estimated resource usage under controlled, reproducible conditions without live network or external LLM dependencies.

## Layout

```text
eval/litebridge/
├── README.md                     # This documentation
├── manifest.json                 # Dataset metadata, file SHA-256 digests, and split counts
├── cases.jsonl                   # 40 hand-authored benchmark cases with independent task requirements
├── fixture_local_evidence.jsonl  # 25 synthetic local document evidence items (includes duplicates & multi-sentence)
├── fixture_web_snippets.jsonl    # 20 synthetic web search snippets with canonical HTTPS URLs
├── splits.json                   # Disjoint partition mapping (12 train, 12 validation, 16 test)
└── expected/
    └── baseline_schema.json      # JSON Schema for evaluation report validation
```

## Dataset Splits

The benchmark defines 40 cases partitioned into three strictly disjoint splits:

| Split        | Cases | Purpose |
| ------------ | ----- | ------- |
| `train`      | 12    | Model fitting for offline learned-controller experiment only |
| `validation` | 12    | Hyperparameter selection and heuristic baseline comparison |
| `test`       | 16    | Single held-out final evaluation (never seen during fitting/selection) |

## Case Categories

The 40 cases cover:
- **Local technical documentation queries:** FastEmbed embeddings, BM25 indexing, Qdrant storage, FastAPI backend, OpenTelemetry tracing.
- **Freshness / web queries:** Modern 2026 technical updates and specifications with explicit query consent (`allow_external_query=True`).
- **Local reference cue queries:** Queries explicitly mentioning local file paths (`docs/`, `config.json`).
- **Unanswerable queries:** Out-of-domain queries where no evidence exists (`expected_answerable=False`, `expected_stop_reason="no_candidates"`).
- **Ambiguous queries:** Ungrounded queries requiring graceful fallback.
- **Compression-sensitive queries:** Queries retrieving multi-sentence and duplicate evidence records to test extractive pruning and deduplication without dropping expected evidence.
- **Explicit source selection:** Queries providing explicit `source_id` parameters.
- **Blocked budget queries:** Queries with zero retrieval calls or zero web calls (`expected_stop_reason="budget_exceeded"`).
- **Blocked consent queries:** Queries with web freshness cues but external consent denied (`expected_stop_reason="blocked_policy"`).

## Integrity Verification

The evaluation runner verifies the SHA-256 digest of every file against `manifest.json` before executing any baseline. If any file has been modified or if split overlap is detected, evaluation halts immediately with `ManifestIntegrityError`.

## Limitations

1. **Synthetic fixtures:** Fixtures are hand-authored, technical markdown excerpts and snippets, not live web crawls.
2. **Zero live network calls:** No requests are made to Tavily, OpenAI, Anthropic, Gemini, Ollama, or remote databases.
3. **Deterministic token/cost estimates:** Token counts are estimated using the standard 4-character approximation. Cost is computed from configured source micro-USD rates.
4. **No semantic entailment claim:** Metric calculations verify structural citation integrity and evidence recall, not LLM semantic grounding.
5. **Learned controller is offline-only:** The learned controller is an exploratory candidate evaluated against frozen splits and is not adopted for runtime deployment.

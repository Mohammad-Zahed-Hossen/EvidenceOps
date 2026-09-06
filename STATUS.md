# Project Status

## Current status: Phase 5 complete and locally verified

Phase 0, Phase 1A, Phase 1B, Phase 1C, Phase 2, Phase 3, Phase 4, and Phase 5 are complete.
Phase 5 completion evidence, API endpoints, bounded concurrency controls, and
dashboard implementation are recorded in [the handoff](docs/status/phase-5-handoff.md).
Phase 6 has not started.

## Roadmap

- [x] Phase 0: environment and repository preflight.
- [x] Phase 1A: domain contracts and configuration.
- [x] Phase 1B: ingestion and chunking.
- [x] Phase 1C: persisted local BM25, FastEmbed/Qdrant, RRF and FlashRank implementation.
- [x] Phase 2: shared documentation service and exactly three allowlisted local STDIO MCP tools.
- [x] Phase 3: validated bounded graph, explicit retrieval/fallback/reranking, sufficient
  grounded context, local generation, citation validation/one repair, structured abstention,
  QueryService and CLI; real local runtime verification passed.
- [x] Phase 4: evaluation dataset, baseline benchmarking (NaiveDenseRAG, BM25RAG, TwoStepHybrid),
  controller training/fallback, paired bootstrap statistical significance, reproducible
  run manifests/leaderboards, and strictly-redacted local OpenTelemetry tracing.
- [x] Phase 5: FastAPI backend and recruiter-facing observability dashboard.
- [ ] Phase 6: release hardening and portfolio packaging.

## Verified results (Phase 5)

- Default unit test suite: 410 passed, 1 Windows symlink skip.
- API and dashboard test suite: 25 unit/contract tests passing (`test_health_metrics.py`, `test_query_api.py`, `test_eval_api.py`, `test_dashboard_contract.py`).
- Concurrency & bounds: Enforced `api_max_concurrent_queries=1`, `api_max_concurrent_evaluations=1`, query length `[2..2000]`, and `api_run_history_limit=100`.
- Security & isolation: Loopback binding `127.0.0.1:8080`, sanitized error envelopes, complete traceback and local path redaction, zero external CDNs or external web fonts in dashboard.
- Async evaluation runner: Bounded background evaluation execution via allowlist-validated `POST /v1/eval/run` and non-blocking polling via `GET /v1/eval/{evaluation_id}`.
- Desktop automation: One-click launcher `EvidenceOps.bat` and `scripts/run_app.ps1` with automated Qdrant/Ollama/FastAPI startup, dedicated browser app mode, and clean teardown/memory reclaim.
- Linting & Typing: Ruff check, ruff format, and Mypy passed with zero errors.

## Next action

Await user review of Phase 5 implementation and handoff documentation.
Do not commit or push Git changes without explicit user authorization.
Following approval, proceed to Phase 6: release hardening and portfolio packaging.

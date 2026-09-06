# Project Status

## Current status: Phase 4 complete and locally verified

Phase 0, Phase 1A, Phase 1B, Phase 1C, Phase 2, Phase 3, and Phase 4 are complete.
Phase 4 completion evidence, benchmark methodology, baseline comparisons, and
local observability are recorded in [the handoff](docs/status/phase-4-handoff.md).
Phase 5 has not started.

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
- [ ] Phase 5: FastAPI backend and dashboard.
- [ ] Phase 6: release hardening and portfolio packaging.

## Verified results (Phase 4)

- Default unit test suite: 385 passed, 1 Windows symlink skip, 6 marked live tests deselected.
- Full evaluation test suite: 40 evaluation unit tests + 6 observability unit tests passing.
- Phase 4 integration tests: Passing with mock systems and live smoke runner.
- Live local Ollama (`qwen2.5:1.5b`) & Qdrant verification: Verified live smoke benchmark run.
- Ruff lint/formatting, mypy strict type check (84 source files) pass with zero errors.
- Default model artifact: Serialized to `artifacts/models/controller_model.joblib`.
- Reproducible run artifacts: Emitted to `eval/runs/<run_id>/manifest.json` and `leaderboard.md`.

## Next action

Await user review of Phase 4 implementation and handoff documentation.
Do not commit or push Git changes without explicit user authorization.
Following approval, proceed to Phase 5: FastAPI backend and local observability dashboard.


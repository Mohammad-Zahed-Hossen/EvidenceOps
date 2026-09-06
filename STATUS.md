# Project Status

## Current status: Phase 3 complete and locally verified

Phase 0, Phase 1A, Phase 1B, Phase 1C implementation, Phase 2 MCP Foundation and
Phase 3 bounded LangGraph orchestration are complete. Phase 3 completion evidence,
interfaces, limits and limitations are recorded in [the handoff](docs/status/phase-3-handoff.md).
The early orchestration handoff is superseded. Phase 4 has not started.

The separate Phase 1C 30-question human judgment gate remains **pending**. The
recorded inspection document and Phase 1C/2 handoffs still contain pending labels;
no recorded human acceptance was found. Corpus scope was provisionally approved,
but this does not establish final judgment acceptance. No measured retrieval-quality
improvement is claimed from Phase 3 smoke testing.

## Roadmap

- [x] Phase 0: environment and repository preflight.
- [x] Phase 1A: domain contracts and configuration.
- [x] Phase 1B: ingestion and chunking.
- [x] Phase 1C: persisted local BM25, FastEmbed/Qdrant, RRF and FlashRank implementation.
- [x] Phase 2: shared documentation service and exactly three allowlisted local STDIO MCP tools.
- [x] Phase 3: validated bounded graph, explicit retrieval/fallback/reranking, sufficient
  grounded context, local generation, citation validation/one repair, structured abstention,
  QueryService and CLI; real local runtime verification passed.
- [ ] Phase 4: evaluation, benchmarking and local observability.
- [ ] Phase 5: FastAPI backend and dashboard.
- [ ] Phase 6: release hardening and portfolio packaging.

## Verified results (2026-09-05/06)

- Default suite: 372 passed, 1 Windows symlink-permission skip, 5 marked tests deselected.
- Coverage: 90.79%, exceeding the required 75%.
- Ruff lint/format, mypy (55 source files) and Git diff checks pass.
- Native Ollama marker: 1 passed with qwen2.5:1.5b.
- Local Qdrant marker: 1 passed.
- Combined local pipeline marker: 1 passed, including actual dense retrieval,
  FlashRank reranking, grounded generation and packed-context citation membership.
- Five serial CLI checks: conceptual answer and greeting completed; identifier query
  abstained after failed citation repair; comparison stopped on unchanged evidence;
  unsupported question abstained without generation. These are smoke tests, not benchmarks.

Default tests do not require daemons or model downloads. Live tests use native Ollama
at localhost:11434/v1, the existing local corpus/indexes and only the Qdrant container.
The combined smoke uses a 4,000-character/two-chunk context. Defaults retain hard ceilings
of 24,000 characters/six chunks, three calls/iterations and two generations. The 1.5B
model can omit citations; strict validation may abstain. Larger contexts can time out.

Cleanup: Ollama is unloaded. Docker Desktop was already stopped at final cleanup;
Qdrant has no listener on port 6333. Compose could not inspect its saved container
state with the engine down. Existing model weights and indexes were preserved.

## Next action

Review the uncommitted Phase 3 diff and handoff. No commit or push has been performed.
After approval and integration, start Phase 4 by specifying fixed development/held-out
questions, gold facts/supporting IDs and reproducible baseline identities under SSOT
section 12. Reconcile the outstanding human judgments before claiming retrieval quality.

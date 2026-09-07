# Project Status

## Current status: Phase 6 complete and locally verified

Phase 0, Phase 1A, Phase 1B, Phase 1C, Phase 2, Phase 3, Phase 4, Phase 5, and Phase 6 are complete.
Phase 6 release hardening, recruiter-facing trajectory dashboard, deterministic operational smoke suite,
CPU-safe profile validation, and portfolio documentation are recorded in [the Phase 6 final audit](docs/status/phase-6-final-audit.md).

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
- [x] Phase 6: release hardening, reproducibility, recruiter dashboard UX, documentation, and portfolio packaging.

## Verified results (Final Polish & Paused Release Candidate)

- Comprehensive test suite: 509 passed tests, 1 Windows symlink skip, 0 failures.
- Code quality & formatting: Ruff check (181 files), ruff format (181 files), and Mypy (87 files) pass with zero errors. Test coverage: > 90% (exceeds 75% requirement).
- Local generation provider boundary: Framework-independent `GenerationProvider` protocol with default `OllamaGenerationProvider` and strictly loopback-only `OpenAICompatibleLocalProvider` (LM Studio / vLLM on `127.0.0.1` / `localhost`). External hosts, HTTPS, and API keys are strictly rejected.
- Evaluation split-family integrity: Deterministic `fact_family_id` partition across 52 distinct families eliminating all cross-split fact leakage between dev, val, and test splits (60/20/20). Dev-only controller training enforced; learned controller achieves 100% agreement with heuristic controller on the 20-item test split.
- Recruiter dashboard UX: 5-stage chronological visual trajectory flow, interactive sample benchmark pills, collapsible citation cards with safe URL rendering, structured evaluation comparison table, zero `.innerHTML`, and responsive layout down to 390 px.
- Strict security & model isolation: `local_models_only=True` enforced at API and evaluation boundaries, loopback binding `127.0.0.1:8080`, strict sanitized error envelopes without raw tracebacks, and complete span telemetry redaction.
- CPU-safe profile validation: 8 GB RAM target verified; total measured EvidenceOps process-component footprint under 1.4 GB (API ~62 MB, Qdrant ~45 MB, Ollama ~1.2 GB), with bounded query concurrency = 1 and max 3 retrieval calls.
- Automated lifecycle: One-click launcher scripts (`EvidenceOps.bat` and `scripts/run_app.ps1`) orchestrate Qdrant, Ollama, and FastAPI, opening dedicated app mode and cleanly terminating/unloading models on exit.

## Next action

Work is paused. Repository is packaged as an honest, defensible portfolio release candidate.
Awaiting user instructions for Git operations or portfolio presentation.

---

## LiteBridge Experimental Track

### Status: Architecture guardrail amendment complete; Phase L1 pending

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch.

- **Branch Name:** `experiment/litebridge-bridge`
- **Baseline Commit:** `1c490dc65e57c3e38766d466755b95e359f10ca5`
- **Phase L0 & Guardrails Status:** Complete and verified (pre-L1 architecture amendment complete)
- **Phase L1 Status:** Not yet implemented. Phase L1 may begin only under the new core/port/adapter guardrails.

- **Documents Created & Updated in this Amendment:**
  - `LiteBridge_SSOT.md` (updated to v1.1: product identity, core-port-adapter boundary, layout, phase amendments, extraction gate)
  - `docs/architecture/LiteBridge_L0_Architecture_Baseline.md` (updated: adapter-only capability matrix, architecture guardrail amendment, updated resume guide)
  - `docs/architecture/LiteBridge_Phase_Gates.md` (new: non-negotiable invariants, phase-start/phase-completion checklists, phase stop rules)
  - `AGENTS.md` (added: LiteBridge architecture guardrails)
  - `DECISIONS.md` (added: ADR-026 on core-port-adapter boundary and extraction policy)
  - `STATUS.md` (updated: architecture amendment status and guardrails)
  - `README.md` (updated: accurate architecture note on experimental branch scope)

- **Verification Commands & Baseline Results:**
  - `uv run pytest -ra -q`: 509 passed, 1 skipped (Windows symlink privilege)
  - `uv run ruff check src tests scripts`: All checks passed
  - `uv run ruff format --check src tests scripts`: 182 files already formatted
  - `uv run mypy src/evidenceops`: Success (no issues found in 87 source files)
  - `git diff --check`: Clean

- **EvidenceOps No-Change Guarantee:** Zero modifications to existing EvidenceOps runtime behaviors, CLI commands, API routes, MCP tools, database schemas, evaluation datasets, or generation provider behavior. `main` branch remains protected and untouched. No runtime code, dependencies, datasets, or EvidenceOps behavior changed.

- **Explicit Next Approved Action:**
  `L1 — Generator-Independent Context Mode, using a LiteBridge-owned retrieval port and an isolated EvidenceOps adapter.`

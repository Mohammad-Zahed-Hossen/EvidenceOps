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

### Status: Phase L9 completed and locally verified

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Phase L9 (Release Hardening).
- **Phase L7 Summary (Completed):** Phase L7 (API, SDK, and MCP Interfaces) certified with 10 mandatory safety corrections, opaque handles, server-owned models, dual consent, and strict MCP validation.
- **Phase L8 Summary (Completed):** Phase L8 (Evaluation and Learned Controller) certified with 40 frozen cases, 3 disjoint splits, 100% support-preservation rate, and offline-only learned controller non-adoption.
- **Phase L9 Implementation Summary:**
  - **Dedicated Security Suite:** Added 21 focused security tests in `tests/security/` covering prompt injection isolation (`[UNTRUSTED_RETRIEVED_DATA]`), API request model strictness (`extra="forbid"`), provider failure sanitization (zero leaked secrets or paths), single-invocation guarantees, core-port-adapter import boundary decoupling, and fresh-process isolation.
  - **Tracked-Text Secret Scanner:** Implemented safe scanner in `scripts/verify_litebridge_release.py` that scans `git ls-files` text paths, rejects `.env` before any read, and confirms zero detected tracked secrets.
  - **Offline Release Invariant Verifier:** `scripts/verify_litebridge_release.py` operates 100% offline without live network calls, confirms L8 manifest SHA-256 integrity, and verifies run-to-run determinism digest equality (`1ba50be0137cc479a9fc92602090bf35a2e5d65ecf0328c5238653879478aa2b`).
  - **Truthful Documentation:** Documented non-claims regarding syntactic citations vs. semantic support, synthetic fixture vs. production web scale, and deferred direct-page retrieval.
- **Verification Results:**
  - Security suite: 21 passed in `tests/security/`.
  - Bridge and eval suites: 252 passed in `tests/unit/bridge/` and `tests/unit/eval/`.
  - Full test suite: 789 passed, 1 skipped (Windows symlink privilege), 0 failures.
  - Code quality: Ruff check and ruff format pass with zero errors (264 files clean).
  - Type checking: Mypy passes with zero issues (126 source files).
  - Release verifier: `scripts/verify_litebridge_release.py` exits 0 with zero findings.
- **Next Action:**
  All LiteBridge development phases (L1–L9) are complete, verified, and release-hardened on `experiment/litebridge-bridge`. Ready for experimental release.

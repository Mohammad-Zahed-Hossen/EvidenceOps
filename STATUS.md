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

### Status: Phase L8 completed and locally verified

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Phase L8 (Evaluation and Learned Controller).
- **Phase L7 Summary (Completed):** Phase L7 (API, SDK, and MCP Interfaces) certified with 10 mandatory safety corrections, opaque handles, server-owned models, dual consent, and strict MCP validation.
- **Phase L8 Implementation Summary:**
  - **Frozen Benchmark Corpus:** 40 hand-authored cases partitioned into strictly disjoint splits (12 train, 12 validation, 16 test) with zero live network calls. Supported by static JSONL fixtures for local documentation (`fixture_local_evidence.jsonl`) and web search snippets (`fixture_web_snippets.jsonl`).
  - **Manifest Verification:** Cryptographic SHA-256 validation (`eval/litebridge/manifest.json`) fails closed immediately on any fixture modification or split tampering.
  - **Multi-Connector Portability Conformance:** `EvidenceOpsLocalRetrieverAdapter` conforms to identical retrieval contracts as the static fixture retriever using a `FakeLocalDocumentationService`.
  - **Seven Evaluation Baselines:** Evaluates `no_retrieval`, `fixed_local`, `fixed_web`, `heuristic_planner`, `heuristic_plus_compression`, `learned_planner_experiment`, and `evidenceops_adapter_conformance` under identical query conditions.
  - **Support-Preservation Invariant:** 100% support-preservation rate across all answerable cases under extractive compression; runner fails closed if support drops.
  - **Deterministic Repeatability:** Runner computes a stable `determinism_digest` across all non-timing report fields, ensuring run-to-run verification without timestamp drift.
  - **Latency Distribution:** Deterministic 10-pass benchmarking measures p50, p90, p95, and p99 latency without single-run volatility.
  - **Learned Controller Predeclared Non-Adoption Gate:** Evaluated an offline `LogisticRegression(random_state=42)` classifier on the 12-case validation split. Because 12 cases cannot establish safe production superiority over the deterministic heuristic, the model is recorded as an offline candidate only and runtime adoption is deferred.
- **Verification Results:**
  - Focused evaluation & bridge tests: 252 passed, 0 failures (`tests/unit/eval/` and `tests/unit/bridge/`).
  - Full test suite: 768 passed, 1 skipped (Windows symlink privilege), 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors (259 files clean).
  - Type checking: Mypy passes with zero issues (126 source files).
  - Reproducibility: Determinism digest `1ba50be0137cc479a9fc92602090bf35a2e5d65ecf0328c5238653879478aa2b` reproduced identically across independent runs.
- **Known Limitations & Deferred Milestones:**
  - Synthetic routing corpus (40 cases) is an offline benchmark, not real-world web scale.
  - Multi-hop retrieval and multi-source evidence fusion remain deferred.
  - Direct web page retrieval remains a Deferred Security Milestone.
- **Next Phase:**
  `Phase L9 — Release Hardening`.

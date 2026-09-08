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

### Status: Complete and verified — deterministic planner and budget policy (Phase L4)

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Phase L4 (Deterministic Planner and Hard Budget Policy).
- **Phase L4 Completion Status:**
  - **Deterministic Single-Action Planner**: Implemented `DeterministicPlanner` which analyzes query features (freshness cues, explicit temporal years, local technical reference cues) and policies to route queries to exactly one registered source (`LOCAL`, `WEB`) or emit `BLOCKED`. Zero LLM calls, zero agent loops, zero speculative retries, and complete generator independence.
  - **Budget Authority Separation**: `RetrievalPolicy` exclusively owns context character and token ceilings (`max_context_chars`, `max_estimated_tokens`), while `BudgetPolicy` exclusively owns execution calls, cost, and wall-clock ceilings (`max_retrieval_calls`, `max_web_calls`, `max_wall_clock_ms`, `max_estimated_external_cost_microusd`).
  - **Hard Preflight Budgets**: Call limits and estimated cost limits are enforced preflight before any retrieval action. Zero allowed calls immediately returns a blocked empty package.
  - **Bounded Web Timeout**: Web retrieval network timeout is clamped against `policy.budget.max_wall_clock_ms`.
  - **Post-Execution Wall-Clock Reporting**: Synchronous local retrieval evaluates wall clock post-execution and emits `StopReason.BUDGET_EXCEEDED` with a sanitized fixed warning if the budget was exceeded.
  - **Accurate Web Cost Accounting**: External cost is charged only for actual web calls: `estimated_external_cost_microusd = descriptor.estimated_external_cost_microusd * actual_web_calls`. In-memory cache hits incur 0 external cost (`web_calls = 0`, `estimated_external_cost_microusd = 0`).
  - **SourceRegistry Encapsulation**: Retriever resolution remains strictly internal (`resolve()`). Callers inspect read-only descriptors (`get_descriptor`, `default_descriptor`, `has_source`) without bypassing planning or budget guardrails.
  - **Deterministic Package Identity**: `package_id` incorporates planner route, reason codes, and effective budget parameters, while strictly omitting non-deterministic execution timings (`wall_clock_ms`) and usage values (`budget_used`).
- **Deliverables:**
  - `src/evidenceops/bridge/contracts.py`: Added `BudgetPolicy`, `PlannerRoute`, `PlannerReason`, `QueryFeatures`, `PlannerDecision`, and budget/planner package fields.
  - `src/evidenceops/bridge/budget.py`: `BudgetGuard` enforcing preflight checks, web-call cost calculation, and post-execution wall-clock evaluation.
  - `src/evidenceops/bridge/planner.py`: Query feature extractor and `DeterministicPlanner` single-action routing engine.
  - `src/evidenceops/bridge/source_registry.py`: Read-only descriptor lookup methods (`get_descriptor`, `default_descriptor`, `has_source`, `list_descriptors`).
  - `src/evidenceops/bridge/context_builder.py`: Blocked package constructor and deterministic package identity incorporating planner decisions.
  - `src/evidenceops/bridge/service.py`: Core `prepare_context()` integration with preflight budget checks, single-source dispatch, cost accounting, and post-execution wall-clock reporting.
  - `src/evidenceops/settings.py`: Added `litebridge_tavily_search_estimated_cost_microusd = 8000`.
  - `src/evidenceops/bridge/factory.py`: Wired source cost metadata (local = 0 uUSD, Tavily = 8000 uUSD).
  - `src/evidenceops/bridge/adapters/web_retriever.py`: Clamped `max_results` by `max_evidence_items` and `timeout_ms` by `max_wall_clock_ms`.
- **Verification Results:**
  - Focused bridge tests: 138 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 647 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors (211 files).
  - Type checking: Mypy passes with zero issues (102 source files).
  - AST audit: `test_generator_independence.py` confirms zero generator or EvidenceOps imports in `planner.py` or `budget.py`.
- **Known Limitations & Deferred Milestones:**
  - Query decomposition, iterative multi-hop retrieval, and multi-source evidence fusion are deliberately deferred to future phases.
  - **Deferred Security Milestone (Direct Web Page Retrieval)**: Arbitrary direct web page fetching remains excluded until a proven DNS-pinning/rebinding defense is designed.
  - Zero external LLM provider adapters (OpenAI, Anthropic, Gemini).
  - Context packaging only; answer generation (`answer()`) is not implemented.
- **Next Phase:**
  `L5 — External LLM Provider Adapters` (UNBLOCKED).

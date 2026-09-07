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

### Status: Complete and verified — snippet-only web retrieval

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Rescoped L3 (Snippet-only web search retrieval; direct page fetching deferred).
- **Phase L3 Completion Status:**
  - **Snippet-Only Web Retrieval Verified**: Rescoped Phase L3 to provider-neutral search snippet retrieval (initially backed by Tavily Basic Search). All direct page fetching (`SafeWebPageFetcher`, `WebPageFetcher`, `FetchedWebPage`, `SourceKind.WEB_PAGE_EXCERPT`, domain allowlists, redirect limits) has been completely removed from the active runtime, configuration, and tests.
  - **Local-First Default**: Default operation requires zero API keys, makes zero network calls, and registers no web sources.
  - **Strict Opt-In Web Retrieval**: Web snippet queries go to the configured search provider only after explicit opt-in: `ExecutionProfile.HYBRID`, selected `tavily_web_search` source, `WebRetrievalPolicy(allow_external_query=True)`, `LITEBRIDGE_ENABLE_TAVILY_WEB=true`, and `TAVILY_API_KEY`.
  - **Core Import Decoupling**: Core modules contain zero imports of `httpx`, `requests`, `urllib`, `socket`, `importlib`, or LLM providers, verified by AST import audits.
  - **Zero Attack Surface for Untrusted URLs**: The active L3 product makes zero outbound connections to search-result URLs; its sole external network operation is bounded requests to the fixed Tavily Search API endpoint.
  - **Sanitized Errors and Provenance**: Error messages strictly avoid leaking secrets, query text, or filesystem paths. Search results preserve canonical URL citations and untrusted evidence boundaries.
  - **Thread-Safe In-Memory Cache**: `WebRetrievalCache` protects cached snippet batches with `threading.RLock()`. Cache hits make 0 provider calls (`web_calls == 0`).
- **Deliverables:**
  - `src/evidenceops/bridge/contracts.py`: Public contracts with `SourceKind.WEB_SEARCH_SNIPPET`, snippet `WebRetrievalPolicy`, and URL-provenance `EvidenceRecord`.
  - `src/evidenceops/bridge/ports.py`: Provider-neutral `WebSearchProvider` protocol and `WebSearchHit` models.
  - `src/evidenceops/bridge/adapters/tavily_search.py`: Isolated Tavily search adapter with sanitized error handling.
  - `src/evidenceops/bridge/adapters/web_cache.py`: Thread-safe bounded LRU TTL cache.
  - `src/evidenceops/bridge/adapters/web_retriever.py`: Snippet-only `WebRetrieverAdapter` with policy-to-settings clamping.
  - `src/evidenceops/bridge/factory.py`: Composition root registering web search only when enabled with valid credentials.
- **Verification Results:**
  - Focused bridge tests: 111 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 620 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors.
  - Type checking: Mypy passes with zero issues.
  - Zero runtime references: AST and import tests verify page-fetch classes and modules are completely absent.
  - Generator independence: Proven by exploding-stub tests across all retrieval modes.
- **Known Limitations & Deferred Milestones:**
  - **Deferred Security Milestone (Direct Web Page Retrieval)**: Direct arbitrary web page fetching is excluded from active LiteBridge runtime and deferred to a dedicated future security-hardening milestone requiring a robust, stable DNS-pinning / rebinding defense design.
  - Single-source selection only per call; no multi-source query planning, fan-out, or evidence fusion across local and web simultaneously.
  - Declarative timeouts (`timeout_ms`) with zero retries; hard process cancellation is not implemented.
  - Zero external LLM provider adapters (OpenAI, Anthropic, Gemini).
  - Context packaging only; answer generation (`answer()`) is not implemented.
- **Next Phase:**
  `L4 — Planner and Budget Policy` (UNBLOCKED).

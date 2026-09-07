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

### Status: Phase L3 complete and locally verified

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Baseline Commit for L3:** `5a5bde1`
- **Phase L3 Completion Status:** Complete and verified (safe opt-in web search and page retrieval, SSRF protection, domain allowlists, generator-independent).
- **Deliverables Implemented:**
  - `src/evidenceops/bridge/contracts.py`: Added `SourceKind.WEB_SEARCH_SNIPPET`, `SourceKind.WEB_PAGE_EXCERPT`, `PrivacyClassification.PUBLIC_WEB`, `SourceFreshness.LIVE`, `WebRetrievalPolicy`, `validate_canonical_https_url`, `supported_execution_profiles` on `SourceDescriptor`, web provenance fields on `EvidenceRecord`, and `web_calls` on `ContextPackage`.
  - `src/evidenceops/bridge/ports.py`: Added `WebSearchHit`, `FetchedWebPage`, protocols `WebSearchProvider` and `WebPageFetcher`, web provenance fields on `RawEvidenceCandidate`, and `web_calls` on `RetrievalBatch`.
  - `src/evidenceops/settings.py` & `.env.example`: Added 10 LiteBridge web settings with strict hostname-only domain validation and `parsed_allowed_fetch_domains`.
  - `src/evidenceops/bridge/adapters/tavily_search.py`: Isolated `TavilySearchAdapter` translating Tavily Basic Search API into `WebSearchHit` records without exposing API keys in error representations.
  - `src/evidenceops/bridge/adapters/safe_web_fetcher.py`: SSRF-safe `SafeWebFetcher` enforcing HTTPS-only, no credentials, port 443 only, no URL fragments, no IP literals, pre-request DNS resolution rejecting non-globally-routable IPs, manual redirect hop validation (max 3), content-type verification, response streaming byte caps, and stdlib HTML text extraction.
  - `src/evidenceops/bridge/adapters/web_cache.py`: In-memory bounded LRU TTL `WebRetrievalCache` keyed by query and policy hash.
  - `src/evidenceops/bridge/adapters/web_retriever.py`: Coordinated `WebRetrieverAdapter` enforcing policy-to-settings caps, caching with `web_calls=0` accounting, and graceful fallback to snippets on fetch failure.
  - `src/evidenceops/bridge/source_registry.py`: Extended to support `ExecutionProfile.HYBRID` and validate source descriptor `supported_execution_profiles`.
  - `src/evidenceops/bridge/service.py`: Enforces 5-part web opt-in requirements, rejects web policy under `LOCAL_ONLY`, validates candidate kinds allowing both snippets and page excerpts for web sources, forwards `web_calls` accounting, and maintains deterministic package identity.
  - `src/evidenceops/bridge/factory.py`: Composition root conditionally registering `tavily_web_search` when enabled with API key, while preserving local-only default operation.
  - `src/evidenceops/bridge/__init__.py`: Exported `WebRetrievalPolicy`.
- **Verification Results (Post-L3):**
  - Focused L3 tests: 95 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 604 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check (207 files) and ruff format (207 files) pass with zero errors.
  - Type checking: Mypy passes with zero issues across 101 source files.
  - Import audit: AST inspection proves core modules contain zero imports of `httpx`, `requests`, `urllib`, `socket`, `ipaddress`, EvidenceOps internals, or LLM providers; adapter modules contain zero LLM or generation imports.
  - Generator independence: Proven by exploding-stub tests across direct retriever, local registry, and web retriever modes confirming `prepare_context()` succeeds while all generation providers raise if touched.
- **Known L3 Limitations:**
  - Single-source selection only per call; no multi-source query planning, fan-out, or evidence fusion across local and web simultaneously.
  - Declarative timeouts (`timeout_ms`) with zero retries; hard process cancellation is not implemented.
  - Zero external LLM provider adapters (OpenAI, Anthropic, Gemini).
  - Context packaging only; answer generation (`answer()`) is not implemented.
- **Explicit Next Approved Action:**
  `L4 — Hybrid Evidence Fusion`.

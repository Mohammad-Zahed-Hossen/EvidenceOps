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

### Status: L1–L3 Audit Remediated; Documented DNS-Rebinding Residual Risk (L3 not fully security-verified; L4 blocked)

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Baseline Commit for L3:** `5a5bde1`
- **Current Baseline:** `ee2385f` + Remediation (Findings A, B, D, E, F, G resolved and verified; Finding C honest fallback documented).
- **Phase L3 Completion & Remediation Status:**
  - Finding A (Streaming byte cap): Fixed and verified. `SafeWebPageFetcher` streams chunks incrementally via `resp.iter_bytes()` and immediately aborts on exceeding `eff_max_bytes` before materializing the full body.
  - Finding B (Transport policy enforcement): Fixed and verified. `SafeWebPageFetcher` owns client instantiation with `trust_env=False` and `follow_redirects=False`. Callers cannot inject preconfigured `httpx.Client` instances. A private `_transport` parameter serves only as an internal test seam.
  - Finding C (DNS rebinding TOCTOU): Evaluated and documented. `httpx 0.28.1` and `httpcore 1.0.9` expose no version-stable, documented public API for DNS-pinned connections that preserves TLS SNI and certificate verification without hooking private methods. Rather than rely on an unstable private hook, LiteBridge retains defense-in-depth controls (HTTPS-only, strict domain allowlist, port 443, no credentials/fragments, IP-literal rejection, pre-request DNS resolution & global-routable validation, manual redirect validation) and accurately documents the remaining DNS-rebinding TOCTOU residual risk. Phase L3 remains not fully security-verified against TOCTOU rebinding.
  - Finding D (Error and warning sanitization): Fixed and verified. Raw exception text, filesystem paths, IP addresses, backend class names, and secrets are strictly eliminated across public error messages, warnings, and serialized context packages. Recoverable page fetch failures emit only `"A configured page could not be fetched safely."`
  - Finding E (Core import audit): Fixed and verified. AST audit extended to all 6 core files, prohibiting `socket`, `httpx`, `requests`, `urllib`, `importlib`, and dynamic import calls (`__import__`, `importlib.import_module`), with a negative unit test proving detection.
  - Finding F (Documentation alignment): Fixed and verified. Corrected next phase name to `L4 — Planner and Budget Policy` and updated ADR-029 and STATUS.md.
  - Finding G (Cache thread-safety): Fixed and verified. `WebRetrievalCache` operations (`get`, `put`, `clear`, `len`) are protected with `threading.RLock()` and verified under concurrent multi-threaded access.
- **Deliverables Hardened:**
  - `src/evidenceops/bridge/adapters/safe_web_fetcher.py`: SSRF-hardened `SafeWebFetcher` enforcing HTTPS-only, no credentials, port 443 only, no URL fragments, no IP literals, pre-request DNS resolution, streaming byte caps without full buffering, private test transport seam, and sanitized error messages.
  - `src/evidenceops/bridge/adapters/web_cache.py`: Thread-safe bounded in-memory LRU TTL `WebRetrievalCache` with `threading.RLock()`.
  - `src/evidenceops/bridge/adapters/web_retriever.py`: Fixed sanitized warning emission on page fetch failure.
  - `src/evidenceops/bridge/service.py` & `evidenceops_local.py`: Sanitized public exception messages with stable error codes, preserving upstream causes via exception chaining.
- **Verification Results (Post-Remediation):**
  - Focused bridge tests: 111 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 620 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors.
  - Type checking: Mypy passes with zero issues.
  - Core import audit: Proves zero forbidden static imports or dynamic import calls in core modules.
  - Generator independence: Proven by exploding-stub tests across all retrieval modes.
- **Known Limitations:**
  - **DNS Rebinding TOCTOU Residual Risk**: `SafeWebFetcher` pre-validates resolved IPs, but standard `httpx` performs a separate DNS resolution upon TCP socket connection. In the absence of a version-stable, TLS-preserving DNS-pinning extension point in `httpx`/`httpcore`, this residual risk remains explicitly documented. Phase L3 is not fully security-verified.
  - Single-source selection only per call; no multi-source query planning, fan-out, or evidence fusion across local and web simultaneously.
  - Declarative timeouts (`timeout_ms`) with zero retries; hard process cancellation is not implemented.
  - Zero external LLM provider adapters (OpenAI, Anthropic, Gemini).
  - Context packaging only; answer generation (`answer()`) is not implemented.
- **Phase L4 Status:**
  Phase `L4 — Planner and Budget Policy` remains strictly **BLOCKED** until the DNS-rebinding security boundary is resolved or direct page fetching is redesigned/deferred.

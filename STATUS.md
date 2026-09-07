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

### Status: Phase L2 complete and locally verified

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Baseline Commit for L2:** `8125065`
- **Phase L2 Completion Status:** Complete and verified (source-agnostic registry, local source policy, generator-independent).
- **Deliverables Implemented:**
  - `src/evidenceops/bridge/contracts.py`: Added `PrivacyClassification` (`PRIVATE`), `SourceFreshness` (`SNAPSHOT`), `SourceDescriptor`, `SourcePolicy`, and required `source_id: str` on `EvidenceRecord`.
  - `src/evidenceops/bridge/ports.py`: Added required `source_id: str` on `RawEvidenceCandidate`.
  - `src/evidenceops/bridge/errors.py`: Added `LiteBridgeSourceError` and `LiteBridgeTimeoutError`.
  - `src/evidenceops/bridge/source_registry.py`: Core in-memory allowlist source registry with deterministic single default resolution, unique slug enforcement, and strict execution profile checking.
  - `src/evidenceops/bridge/service.py`: `LiteBridge` facade supporting registry mode and backward-compatible direct-retriever mode, single-source policy resolution, candidate source validation, core-governed reproducibility metadata merge, and sanitized timeout mapping.
  - `src/evidenceops/bridge/adapters/evidenceops_local.py`: Isolated adapter configured with `source_id="evidenceops_local_docs"`, propagating `source_id` to candidates, and mapping upstream `TimeoutError` to `LiteBridgeTimeoutError`.
  - `src/evidenceops/bridge/factory.py`: Composition root registering `evidenceops_local_docs` in `SourceRegistry` as default local source with `source_version=None`.
  - `src/evidenceops/bridge/__init__.py`: Clean public exports for L2 contracts and errors.
- **Verification Results (Post-L2):**
  - Focused L2 tests: 59 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 567 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check (200 files) and ruff format (200 files) pass with zero errors.
  - Type checking: Mypy passes with zero issues across 97 source files.
  - Import audit: AST inspection proves all core modules (`contracts.py`, `ports.py`, `errors.py`, `context_builder.py`, `service.py`, `source_registry.py`) contain zero imports of `evidenceops.generation`, `evidenceops.retrieval`, `evidenceops.domain`, or external provider SDKs.
  - Generator independence: Proven by exploding-stub tests in both direct-retriever mode and registry mode confirming `prepare_context()` succeeds while all generation providers and request constructors raise if touched.
- **Known L2 Limitations:**
  - Local documentation corpus only (`SourceKind.LOCAL_DOCUMENT`); single registered production source (`evidenceops_local_docs`).
  - Strict single-source selection per call; no multi-source fan-out, query planning, or evidence fusion.
  - Declarative timeouts (`timeout_ms`) with zero retries; hard process cancellation is not implemented.
  - Zero web search, page fetching, or remote API retrieval.
  - Zero external LLM provider adapters (OpenAI, Anthropic, Gemini).
  - Context packaging only; answer generation (`answer()`) is not implemented.
- **Explicit Next Approved Action:**
  `L3 — Web Search and Page Retrieval`.

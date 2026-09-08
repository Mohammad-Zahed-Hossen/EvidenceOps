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

### Status: L4–L6 independent audit remediation completed pending independent re-audit

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Phase L7 (API, SDK, and MCP Interfaces).
- **Phase L7 Implementation Summary:**
  - **Facade-Only Python SDK:** `LiteBridgeSDK` wraps public facade methods without accessing private registry attributes or adapters.
  - **Opaque Context Handles:** In-memory `InterfacePackageStore` assigns cryptographically random opaque handles (`ctx_<token>`) with TTL eviction; guessed package IDs cannot retrieve packages.
  - **Server-Owned Model Configuration:** API and MCP interfaces reject `model` overrides, arbitrary endpoints, URLs, credentials, and multiple source selection.
  - **Dual Consent for External Retrieval:** Added `LITEBRIDGE_INTERFACE_ALLOW_EXTERNAL_RETRIEVAL=false`; web retrieval requires both server setting and per-call client consent.
  - **Local Boundary Enforcement:** Local API security is guarded by `LocalRequestBoundary` middleware and loopback host configuration (`127.0.0.1`/`localhost`).
  - **Strict MCP Argument Validation:** All FastMCP tool argument models enforce `extra="forbid"`, rejecting unknown arguments prior to execution.
  - **Sanitized Capability Metadata:** Public `/capabilities` endpoint and tool expose only sanitized display names, IDs, enabled status, provider locations, and source kinds.
- **Verification Results:**
  - Focused bridge & interface tests: 244 passed, 0 failures.
  - Full test suite: 747 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors (242 files clean).
  - Type checking: Mypy passes with zero issues (116 source files).
- **Known Limitations & Deferred Milestones:**
  - Multi-hop retrieval and multi-source evidence fusion remain deferred.
  - Direct web page retrieval remains a Deferred Security Milestone.
- **Next Phase:**
  `Phase L8 — Evaluation and Learned Controller`.

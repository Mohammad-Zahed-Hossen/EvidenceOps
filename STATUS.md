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

### Status: Complete and verified — deterministic extractive context compression and quality controls (Phase L6)

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Phase L6 (Deterministic Extractive Context Compression and Quality Controls).
- **Phase L6 Completion Status:**
  - **Deterministic Extractive Compression**: `compress_context()` operates exclusively via complete sentence selection or whole-item retention/dropping. Zero abstractive summarization, zero token cuts mid-sentence, zero rephrasing, and zero LLM calls.
  - **Strict Generator & Retrieval Independence**: `compress_context()` consumes an already-built `ContextPackage` without invoking retrieval, planning, budget computation, or generation. Proven by AST/import audits and exploding mock tests.
  - **Conservative Deduplication Policy**: Exact retrieval duplicate copies (`source_id`, `source_kind`, `document_id`, `chunk_id`, exact normalized excerpt) are only dropped when callers explicitly configure both `allow_evidence_drop=True` AND `deduplicate_exact_retrieval_copies=True`. Defaults are strictly `False`, preserving all evidence.
  - **Final Rendered Context Target Evaluation**: Targets are measured against the full rendered context string (including `UNTRUSTED_CONTENT` wrapper boundaries, headers, citation tags, and closing markers), preventing false budget claims.
  - **Integer Arithmetic for Basis Points**: `(original_tokens - compressed_tokens) * 10_000 // original_tokens` ensures deterministic ratio reporting without floating-point drift.
  - **Citation & Provenance Invariants**: Retained evidence keeps original citation IDs (`[C1]`, `[C3]`) without renumbering. Downstream L5 answers citing dropped citations fail closed with `INVALID_CITATIONS`.
  - **Preserved Retrieval Metadata**: Original retrieval `stop_reason`, `planner_decision`, `budget_used`, and call counters are preserved verbatim. Unmet compression targets are recorded as `CompressionOutcome.TARGET_UNACHIEVABLE`.
  - **Ordered Boundary Concatenation Check**: Quality verification enforces that compressed text is an ordered, non-overlapping sequence of original complete sentences.
- **Deliverables:**
  - `src/evidenceops/bridge/contracts.py`: Added `CompressionStrategy`, `CompressionOutcome`, `CompressionAction`, `CompressionPolicy`, `CompressionTraceEntry`, `CompressionReport`, and updated `ContextPackage`.
  - `src/evidenceops/bridge/context_builder.py`: Added `render_context_text(...)` and incorporated stable compression fields into deterministic `_derive_package_id(...)`.
  - `src/evidenceops/bridge/compressor.py`: Deterministic extractive compressor with conservative sentence splitting and adversarial boundary handling.
  - `src/evidenceops/bridge/quality_controls.py`: Comprehensive quality verification proving non-empty evidence, provenance preservation, non-renumbered citations, non-blank excerpts, ordered boundary concatenation, wrapper boundaries, and unaltered retrieval metadata.
  - `src/evidenceops/bridge/service.py`: Added `LiteBridge.compress_context(...)` facade method.
  - `src/evidenceops/bridge/__init__.py`: Exported public L6 contracts and functions.
- **Verification Results:**
  - Focused bridge tests: 198 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 707 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors (233 files).
  - Type checking: Mypy passes with zero issues (112 source files).
  - AST audit: Proves zero LLM/planner/retrieval imports or invocations in compression modules.
- **Known Limitations & Deferred Milestones:**
  - Public API, SDK packaging, and MCP interfaces are planned for Phase L7.
  - Multi-hop retrieval and multi-source evidence fusion are deferred to future phases.
  - Direct web page retrieval remains a Deferred Security Milestone.
- **Next Phase:**
  `L7 — API, SDK, and MCP Interfaces` (UNBLOCKED).

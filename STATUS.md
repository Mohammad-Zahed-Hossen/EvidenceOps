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

### Status: Complete and verified — optional generation adapters and syntactic citation gating (Phase L5)

LiteBridge is an additive, model-agnostic retrieval and context-preparation middleware layer being developed on a dedicated experimental branch under strict Core-Port-Adapter separation.

- **Branch Name:** `experiment/litebridge-bridge`
- **Current Baseline:** Phase L5 (Optional Generation Adapters and Syntactic Citation Gating).
- **Phase L5 Completion Status:**
  - **Generator-Independent Core Maintained**: `prepare_context()` remains 100% generator-independent with zero provider calls or imports. `answer()` consumes an immutable, already-built `ContextPackage`.
  - **Zero Vendor SDK Dependencies**: No vendor SDKs added to dependencies. All 5 generation adapters (`OllamaGenerationAdapter`, `OpenAICompatibleLocalAdapter`, `OpenAIGenerationAdapter`, `AnthropicGenerationAdapter`, `GeminiGenerationAdapter`) use standard-library typing and internal adapter-owned `httpx.Client(trust_env=False, follow_redirects=False)`.
  - **Strict Local Endpoint Guardrails**: Enforces HTTP-only, literal `127.0.0.1` / `[::1]` or loopback-resolved `localhost`, zero credentials, zero query/fragments, and zero unexpected subpaths via `validate_loopback_url`.
  - **Disabled by Default & Nonblank Validation**: All generation providers are disabled by default. Enabling any provider requires a nonblank model name (and API key for authenticated endpoints).
  - **Privacy Boundary & Per-Call Consent**: Any `LOCAL_DOCUMENT` evidence marks the package private. Hosted providers refuse private evidence with `POLICY_BLOCKED` and `PRIVATE_EVIDENCE_EXPORT_NOT_ALLOWED` unless `allow_private_evidence_export=True` is explicitly passed in `GenerationPolicy`.
  - **Syntactic Citation Validation**: Strictly validates that cited tokens exist in `context_package.evidence` without claiming semantic verification. Strict parser scans all citation-like tokens (`\[[cC][^\]]*\]`); any malformed (`[CX]`, `[C1 ]`, `[C0]`, `[c1]`) or unknown (`[C999]`) token immediately fails closed to `INVALID_CITATIONS` with fixed abstention text.
  - **Deterministic Answer Identity**: Derived deterministically from package ID, provider ID, model ID, normalized policy, final answer text, status, and cited IDs (excluding timings and usage).
  - **Sanitized Failure Boundaries**: `answer()` returns structured `GroundedAnswer` abstentions without leaking raw exception text, URLs, paths, or secrets.
- **Deliverables:**
  - `src/evidenceops/bridge/contracts.py`: Added `ProviderLocation`, `GenerationStatus`, `GenerationAbstentionReason`, `GenerationPolicy`, `ProviderCapability`, `GenerationUsage`, `GroundedAnswer`, and `derive_answer_id(...)`.
  - `src/evidenceops/bridge/ports.py`: Added `GenerationRequest` (with `query: str`), `GenerationResponse`, and `@runtime_checkable class GenerationProvider(Protocol)`.
  - `src/evidenceops/bridge/errors.py`: Added provider error classes.
  - `src/evidenceops/bridge/citation_validator.py`: Pure syntactic citation token extractor and validator.
  - `src/evidenceops/bridge/generation_registry.py`: Pure provider registry decoupled from EvidenceOps internals.
  - `src/evidenceops/bridge/adapters/loopback.py`: Reusable strict loopback HTTP endpoint validator.
  - `src/evidenceops/bridge/adapters/ollama_generation.py`: Native `/api/chat` Ollama generation adapter.
  - `src/evidenceops/bridge/adapters/openai_compatible_local.py`: Local OpenAI-compatible generation adapter.
  - `src/evidenceops/bridge/adapters/openai_generation.py`: Hosted OpenAI generation adapter.
  - `src/evidenceops/bridge/adapters/anthropic_generation.py`: Hosted Anthropic generation adapter.
  - `src/evidenceops/bridge/adapters/gemini_generation.py`: Hosted Gemini generation adapter.
  - `src/evidenceops/bridge/service.py`: Added `LiteBridge.answer(...)` with all privacy, abstention, and citation gating.
  - `src/evidenceops/bridge/factory.py`: Wired optional generation providers (disabled by default).
  - `src/evidenceops/settings.py` & `.env.example`: Added Phase L5 generation configuration settings.
- **Verification Results:**
  - Focused bridge tests: 184 passed, 0 failures (`uv run pytest tests/unit/bridge/ -ra -q`).
  - Full test suite: 693 passed, 1 skipped, 0 failures (`uv run pytest -ra -q`).
  - Code quality: Ruff check and ruff format pass with zero errors (228 files).
  - Type checking: Mypy passes with zero issues (110 source files).
  - AST audit: Proves core and retrieval modules have zero LLM/generation imports, and generation adapters use zero vendor SDKs.
- **Known Limitations & Deferred Milestones:**
  - Context compression, dynamic chunk pruning, and quality metrics are deferred to Phase L6.
  - Multi-hop retrieval and multi-source evidence fusion are deferred to Phase L7.
  - Direct web page retrieval remains a Deferred Security Milestone.
- **Next Phase:**
  `L6 — Context Compression and Quality Controls` (UNBLOCKED).

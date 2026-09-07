# LiteBridge Phase L0: Architecture Baseline and Integration Boundary

## A. Status and Authority

- **Document Phase:** Phase L0 — Branch and Architecture Baseline
- **Status:** Approved Architecture Baseline
- **Authority:** [LiteBridge_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/LiteBridge_SSOT.md) is authoritative for all LiteBridge design, interfaces, and phase roadmap.
- **Reference Authority:** [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md), active source code under `src/evidenceops/`, and active tests under `tests/` remain authoritative for all existing EvidenceOps behavior, guarantees, and verification.
- **Baseline Commit SHA:** `1c490dc65e57c3e38766d466755b95e359f10ca5`
- **Baseline Branch:** `experiment/litebridge-bridge` (branched from `main`)
- **Generation Date:** 2026-09-07

---

## B. Product Boundary

> EvidenceOps remains a complete local-first, evidence-grounded RAG application.
>
> LiteBridge is an additive, generator-independent retrieval, planning, and context-preparation layer that will reuse EvidenceOps through stable boundaries.

LiteBridge is **not yet implemented as a public runtime mode in Phase L0**.

EvidenceOps continues to operate as an independent end-to-end RAG system comprising local document ingestion, BM25 sparse search, FastEmbed/Qdrant dense search, FlashRank reranking, bounded LangGraph controller orchestration, citation-verified generation with Ollama or local OpenAI-compatible endpoints, local evaluation benchmarking, and a local FastAPI/observability dashboard.

LiteBridge does not replace, refactor, or redefine EvidenceOps. In future phases, LiteBridge will live as an experimental middleware layer within `src/evidenceops/bridge/` that leverages EvidenceOps's verified local retrieval, evidence validation, and provider contracts to construct compact, citation-preserving context packages for diverse downstream generators.

---

## C. Integration Boundary

LiteBridge reuses EvidenceOps through stable, high-level public services and protocols. Direct coupling to low-level drivers, internal state machines, or UI layers is strictly forbidden.

### Dependency Rule
```text
LiteBridge → stable EvidenceOps public services / contracts
EvidenceOps core → must not depend on LiteBridge
```

No LiteBridge feature may directly reach into low-level Qdrant client sockets, raw filesystem loaders, internal API route handlers, dashboard code, or provider client connection internals unless a future approved design change explicitly defines a public boundary.

### Capability Integration Matrix

| EvidenceOps Capability | Existing Owning Module(s) (Verified) | LiteBridge Future Use | Allowed Dependency Direction | L0 Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Processed Artifacts / Ingestion** | `evidenceops.ingestion.artifacts`<br>`evidenceops.ingestion.pipeline` | Reuse `JsonProcessedDocumentStore` and `ProcessedDocumentArtifact` to load normalized document chunks and content hashes. | `LiteBridge → Ingestion Public Stores`<br>(EvidenceOps does not depend on LiteBridge) | Read-only access to persisted artifacts under `data/processed/`. No raw parser or file loader modifications. |
| **Sparse Retrieval** | `evidenceops.retrieval.bm25`<br>`evidenceops.retrieval.sparse_store` | Reuse BM25 query execution and snapshot store (`JsonSparseIndexStore`) for exact-match technical lookups. | `LiteBridge → Sparse Store / Protocol`<br>(No reverse dependency) | Reuses existing `SparseRetriever` protocol. No index schema or tokenizer modifications. |
| **Dense Retrieval** | `evidenceops.retrieval.dense`<br>`evidenceops.retrieval.embeddings`<br>`evidenceops.retrieval.qdrant_store` | Reuse `DenseRetrieverService` and `FastEmbedEmbeddingProvider` for semantic vector search against local Qdrant collections. | `LiteBridge → Dense Service Protocol`<br>(No reverse dependency) | No direct `qdrant_client` manipulation. Must use existing service boundaries. |
| **Hybrid Retrieval & Reranking** | `evidenceops.retrieval.hybrid`<br>`evidenceops.retrieval.reranker`<br>`evidenceops.retrieval.service` | Primary entry point: reuse `LocalDocumentationService`, `SearchDocumentationRequest`, `DocumentationSearchResult`, `HybridRetriever`, and `FlashRankReranker`. | `LiteBridge → LocalDocumentationService`<br>(No reverse dependency) | `LocalDocumentationService` is the canonical retrieval boundary for local evidence. |
| **Evidence Adaptation** | `evidenceops.evidence.adapter`<br>`evidenceops.evidence.context`<br>`evidenceops.evidence.sufficiency`<br>`evidenceops.evidence.conflict` | Adapt ranked `RetrievalResult` into candidate `EvidenceRecord`; reuse sufficiency heuristic and pairwise conflict verification. | `LiteBridge → Evidence Public Functions`<br>(No reverse dependency) | No modification to EvidenceOps sufficiency ($S = 0.45R + 0.25C + 0.15D + 0.15A$) or conflict formulas. |
| **Citation Validation** | `evidenceops.evidence.citations` | Reuse sequential citation parser, syntax verification (`[C1]`, `[C2]`), and reference mapping logic. | `LiteBridge → Citation Validator`<br>(No reverse dependency) | Citation contracts and bracket formatting invariants remain identical. |
| **Abstention / Failure Semantics** | `evidenceops.domain.enums`<br>`evidenceops.domain.models`<br>`evidenceops.domain.errors` | Reuse `AbstentionReason`, `RunStatus`, `GroundedAnswer`, and standard error hierarchy (`EvidenceOpsError`). | `LiteBridge → Domain Enums/Models`<br>(No reverse dependency) | LiteBridge errors must inherit from or wrap domain error types without leaking raw backend exceptions. |
| **Generation Provider Contracts** | `evidenceops.generation.contracts`<br>`evidenceops.generation.providers`<br>`evidenceops.generation.ollama` | Reuse `GenerationProvider` protocol, `GenerationRequest`, `GenerationResponse`, and provider factory for downstream answer synthesis. | `LiteBridge → Generation Protocols`<br>(No reverse dependency) | Retains strict loopback-only rule for local providers. Remote providers deferred to Phase L5. |
| **Settings & Configuration** | `evidenceops.settings` | Read application settings (`Settings`, `get_settings`) for local ports, timeouts, thresholds, and ceilings. | `LiteBridge → Settings`<br>(No reverse dependency) | LiteBridge adds no new global settings in L0. L0 inherits existing validated limits. |
| **Evaluation Identities & Artifacts** | `evidenceops.evaluation.identity`<br>`evidenceops.evaluation.artifacts`<br>`evidenceops.evaluation.contracts` | Reuse deterministic SHA-256 fingerprinting (`generate_file_identity`), run manifest models, and benchmark contracts. | `LiteBridge → Evaluation Identity`<br>(No reverse dependency) | Ground-truth datasets and existing benchmarks remain immutable and untouched. |
| **Observability & Tracing** | `evidenceops.observability.tracing` | Reuse `TracingService` and strict `RedactionPolicy` (SHA-256 hashing, zero raw query/text/prompt export). | `LiteBridge → Tracing Service`<br>(No reverse dependency) | No raw text or unredacted traces may cross span boundaries. |

---

## D. Future Public Contract Charter

This section documents the planned public LiteBridge contracts before implementation. **None of these contracts are implemented at runtime in Phase L0.** In particular, `ContextPackage` and `prepare_context()` are strictly Phase L1 deliverables.

### 1. `RetrievalPolicy`
- **Purpose:** Specifies caller constraints on retrieval execution (maximum calls, allowed source kinds, freshness tolerance, reranking mode).
- **Owning Phase:** Phase L1 / Phase L4
- **Required Invariant:** Must enforce bounded call ceilings ($\le 3$ calls in local profile) and deterministic defaults.
- **Forbidden Content:** No raw SQL, no arbitrary regex, no unvalidated network URLs.
- **Generator-Independent:** Yes.

### 2. `GenerationPolicy`
- **Purpose:** Specifies parameters for downstream LLM generation when the caller requests answer synthesis rather than context packaging alone.
- **Owning Phase:** Phase L1 / Phase L5
- **Required Invariant:** Temperature constrained to $[0.0, 1.0]$ (default $0.0$), strict `max_tokens` ceiling ($1 \dots 2048$).
- **Forbidden Content:** No embedded API keys, no system-prompt bypasses, no arbitrary provider endpoint URLs in request bodies.
- **Generator-Independent:** No (applies only during answer generation).

### 3. `SourcePolicy`
- **Purpose:** Controls which source kinds are permitted for a given query (local documents, web search, web fetch, structured API).
- **Owning Phase:** Phase L2 / Phase L3
- **Required Invariant:** In `local_only` profile, non-local sources must be strictly rejected or ignored.
- **Forbidden Content:** Arbitrary hostnames, unapproved external domains, raw IP addresses.
- **Generator-Independent:** Yes.

### 4. `BudgetPolicy`
- **Purpose:** Defines hard cost, token, latency, and call budgets for a LiteBridge execution run.
- **Owning Phase:** Phase L4
- **Required Invariant:** Enforces hard mathematical stops: `max_retrieval_calls`, `max_web_calls`, `max_context_chars`, `max_wall_clock_seconds`.
- **Forbidden Content:** Infinite or negative budgets.
- **Generator-Independent:** Yes.

### 5. `ContextPackage`
- **Purpose:** The core, generator-independent product of LiteBridge. Bounded, citation-preserving context package containing ranked evidence and execution metadata.
- **Owning Phase:** **Phase L1 (Not L0)**
- **Required Invariant:** Must contain immutable package ID, normalized query hash, ordered evidence items with canonical citation IDs (`[C1]`, `[C2]`), token estimates, budget consumption metrics, and stop reason.
- **Forbidden Content:** No secrets, no API keys, no unredacted raw traces, no unbounded text dumps exceeding budget.
- **Generator-Independent:** **Yes (Core product)**.

### 6. `GroundedAnswer`
- **Purpose:** Typed result when an optional generation pass is executed on top of a `ContextPackage`.
- **Owning Phase:** Phase L1 / Phase L5
- **Required Invariant:** Must link directly to the originating `ContextPackage`, report citation validity, and preserve explicit abstention reasons (`insufficient_evidence`, `unsupported_claims`).
- **Forbidden Content:** Unverified factual claims without citation bindings.
- **Generator-Independent:** No.

### 7. `EvidenceRecord`
- **Purpose:** Normalized evidence representation across all source types (local documentation, web snippets, fetched web pages, structured API records).
- **Owning Phase:** Phase L1 / Phase L2
- **Required Invariant:** Must include stable `evidence_id`, `source_kind`, canonical URI/path, title, excerpt, retrieval rank, score, and citation identifier.
- **Forbidden Content:** Active HTML script tags, executable payloads, untrusted prompt instructions treated as system commands.
- **Generator-Independent:** Yes.

### 8. `ExecutionProfile`
- **Purpose:** Enumeration defining the security and connectivity profile: `local_only`, `hybrid`, `hosted`.
- **Owning Phase:** Phase L0 (Charter) / Phase L1 (Runtime)
- **Required Invariant:** Defaults to `local_only`. `local_only` forbids all outbound internet requests.
- **Forbidden Content:** N/A.
- **Generator-Independent:** Yes.

### 9. `SourceKind`
- **Purpose:** Categorizes evidence origin (`local_document`, `web_search_snippet`, `web_page_excerpt`, `structured_api`).
- **Owning Phase:** Phase L1 / Phase L2
- **Required Invariant:** Each kind has explicit citation formatting and trust classification.
- **Forbidden Content:** Undefined or wildcard source kinds.
- **Generator-Independent:** Yes.

### 10. `ProviderCapability`
- **Purpose:** Introspection contract describing supported features of a registered generation provider (context window, tool calling support, local vs hosted, structured outputs).
- **Owning Phase:** Phase L5 / Phase L7
- **Required Invariant:** Read-only, validated capability matrix.
- **Forbidden Content:** Credential fields or auth tokens.
- **Generator-Independent:** No.

### 11. Structured Error / Result Semantics
- **Purpose:** Consistent, sanitized error responses across Python SDK, API, and MCP layers.
- **Owning Phase:** Phase L1 / Phase L7
- **Required Invariant:** Fixed error envelope (`code`, `message`, `details`) with sanitized messages; zero raw stack traces or internal filesystem paths exposed.
- **Forbidden Content:** Raw tracebacks, internal server IPs, credentials, or third-party error dumps.
- **Generator-Independent:** Yes.

---

## E. Execution-Profile Policy

LiteBridge establishes three explicit operating profiles as defined in `LiteBridge_SSOT.md`:

```text
1. local_only (Default in Phase L0)
   - Local processed documents only (BM25, Qdrant on loopback)
   - Local LLM only (Ollama or local OpenAI-compatible on 127.0.0.1 / localhost)
   - Zero outbound web requests; zero external network dependencies
   - Zero external credentials required; strictly CPU-safe (8 GB RAM target)

2. hybrid
   - Local document retrieval combined with approved web search / page fetching
   - Local or hosted generation provider
   - Strict SSRF protection, domain allowlists, and per-request privacy classifications
   - Explicit per-source telemetry and budget accounting

3. hosted
   - Approved web and document connectors
   - Configured external LLM provider (OpenAI, Anthropic, Gemini)
   - Credentials loaded exclusively from system environment or secret managers
   - Strict no-silent-fallback rule: private evidence never sent to external providers
```

### Invariants for Phase L0:
- **Default Profile:** `local_only`.
- **No External Providers:** No external web search provider, page fetcher, or remote LLM adapter is configured or enabled.
- **No Credentials:** Phase L0 introduces zero API keys, zero token secrets, and zero external endpoint settings.
- **Explicit Opt-In Required:** In future phases, transitioning to `hybrid` or `hosted` will require explicit configuration in environment variables; no runtime auto-discovery or silent network fallbacks are permitted.

---

## F. Phase Boundary and Exit Criteria

### Phase L0 Deliverables
1. Dedicated experimental branch created: `experiment/litebridge-bridge`.
2. Existing EvidenceOps baseline locked and verified (509 passing tests, zero regressions).
3. Authoritative specification tracked: `LiteBridge_SSOT.md`.
4. Architecture baseline and integration boundary documented: `docs/architecture/LiteBridge_L0_Architecture_Baseline.md`.
5. Architecture Decision Record recorded: ADR-025 in `DECISIONS.md`.
6. Project status recorded in `STATUS.md`.
7. Project README updated with experimental branch scope notice in `README.md`.
8. Complete pre- and post-change quality gate verification executed.

### Explicit L0 Non-Deliverables
- **No runtime code:** No `src/evidenceops/bridge/` code, no empty scaffolds, and no new modules.
- **No context preparation:** `ContextPackage` and `prepare_context()` are strictly Phase L1.
- **No web retrieval:** Web search, page fetching, SSRF guards, and HTTP client connectors are Phase L3.
- **No external LLM adapters:** OpenAI, Anthropic, Gemini, LM Studio adapters are Phase L5.
- **No new dependencies:** `pyproject.toml` and `uv.lock` remain 100% unchanged.
- **No changes to `main`:** All work is strictly isolated to `experiment/litebridge-bridge`.

### Phase L0 Exit Criteria Checklist
- [x] Dedicated branch `experiment/litebridge-bridge` created from verified `main` commit `1c490dc65e57c3e38766d466755b95e359f10ca5`.
- [x] Tracked working tree has zero modifications against baseline prior to L0 documentation.
- [x] Only approved untracked file `LiteBridge_SSOT.md` is present, verified by SHA-256 (`666be6662c4b12736a76d450dceaa726b3f8b8ff4ab61702afd207dd1b6a2de1`).
- [x] Existing EvidenceOps test suite (`pytest -ra -q`) passes with 509 passed, 1 skipped, 0 failures.
- [x] Linting and type checking (`ruff check`, `ruff format --check`, `mypy`) pass with zero errors.
- [x] Zero dependencies added or modified.
- [x] Zero EvidenceOps runtime behaviors, CLI commands, API routes, or MCP tools modified.
- [x] `main` branch remains untouched and protected.

---

## G. Resume Guide

```text
Next approved implementation phase: L1 — Generator-independent context mode.
```

### Initial Tasks for Phase L1 (from LiteBridge_SSOT.md Section 20):
1. Create `src/evidenceops/bridge/` package namespace.
2. Define `ContextPackage`, `RetrievalPolicy`, and `EvidenceRecord` runtime Pydantic contracts.
3. Implement `prepare_context(query, policy)` facade that executes bounded local retrieval and evidence packaging without invoking an LLM.
4. Adapt `LocalDocumentationService` to populate `ContextPackage` with stable sequential citations (`[C1]`, `[C2]`), token estimates, and stop reasons.
5. Implement unit tests and fake-provider tests verifying generator-independent context preparation.
6. Verify that no LLM generation call occurs when calling `prepare_context()`.

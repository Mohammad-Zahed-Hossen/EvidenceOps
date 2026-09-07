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
| **Processed Artifacts / Ingestion** | `evidenceops.ingestion.artifacts`<br>`evidenceops.ingestion.pipeline` | Reuse `JsonProcessedDocumentStore` and `ProcessedDocumentArtifact` to load normalized document chunks and content hashes. | `LiteBridge Adapter → Ingestion Public Stores`<br>(EvidenceOps does not depend on LiteBridge; core does not access directly) | Read-only access through an isolated adapter (`adapters/evidenceops_local.py`). LiteBridge core logic never accesses filesystem loaders or artifact stores directly. |
| **Sparse Retrieval** | `evidenceops.retrieval.bm25`<br>`evidenceops.retrieval.sparse_store` | Reuse BM25 query execution and snapshot store (`JsonSparseIndexStore`) for exact-match technical lookups. | `LiteBridge Adapter → Sparse Store / Protocol`<br>(No reverse dependency; core decoupled) | Accessed solely via adapter implementing LiteBridge port. LiteBridge core never imports BM25 index schemas or tokenizers. |
| **Dense Retrieval** | `evidenceops.retrieval.dense`<br>`evidenceops.retrieval.embeddings`<br>`evidenceops.retrieval.qdrant_store` | Reuse `DenseRetrieverService` and `FastEmbedEmbeddingProvider` for semantic vector search against local Qdrant collections. | `LiteBridge Adapter → Dense Service Protocol`<br>(No reverse dependency; core decoupled) | No direct `qdrant_client` manipulation. Accessed solely via adapter implementing LiteBridge port. |
| **Hybrid Retrieval & Reranking** | `evidenceops.retrieval.hybrid`<br>`evidenceops.retrieval.reranker`<br>`evidenceops.retrieval.service` | Primary entry point: reuse `LocalDocumentationService`, `SearchDocumentationRequest`, `DocumentationSearchResult`, `HybridRetriever`, and `FlashRankReranker`. | `LiteBridge Adapter → LocalDocumentationService`<br>(No reverse dependency; core decoupled) | `LocalDocumentationService` is accessed solely through `EvidenceOpsLocalRetrieverAdapter`. LiteBridge core imports only LiteBridge ports. |
| **Evidence Adaptation** | `evidenceops.evidence.adapter`<br>`evidenceops.evidence.context`<br>`evidenceops.evidence.sufficiency`<br>`evidenceops.evidence.conflict` | Adapt ranked `RetrievalResult` into candidate `EvidenceRecord`; reuse sufficiency heuristic and pairwise conflict verification. | `LiteBridge Adapter → Evidence Public Functions`<br>(No reverse dependency; core decoupled) | Translated within the adapter layer into LiteBridge-neutral records. LiteBridge core contracts never expose EvidenceOps internal candidate types. |
| **Citation Validation** | `evidenceops.evidence.citations` | Reuse sequential citation parser, syntax verification (`[C1]`, `[C2]`), and reference mapping logic. | `LiteBridge Core / Adapter → Citation Logic`<br>(No reverse dependency) | Citation semantics and bracket formatting invariants (`[C1]`, `[C2]`) are adopted as LiteBridge core contracts without exposing EvidenceOps models. |
| **Abstention / Failure Semantics** | `evidenceops.domain.enums`<br>`evidenceops.domain.models`<br>`evidenceops.domain.errors` | Reuse `AbstentionReason`, `RunStatus`, `GroundedAnswer`, and standard error hierarchy (`EvidenceOpsError`). | `LiteBridge Adapter / Errors → Domain Enums/Errors`<br>(No reverse dependency; core decoupled) | LiteBridge defines its own sanitized error hierarchy (`errors.py`). Adapters map EvidenceOps exceptions into LiteBridge errors. |
| **Generation Provider Contracts** | `evidenceops.generation.contracts`<br>`evidenceops.generation.providers`<br>`evidenceops.generation.ollama` | Reuse `GenerationProvider` protocol, `GenerationRequest`, `GenerationResponse`, and provider factory for downstream answer synthesis. | `LiteBridge Provider Adapter → Generation Protocols`<br>(No reverse dependency; core decoupled) | Retains strict loopback-only rule. Generation adapters are optional Phase L5 components; `prepare_context()` never calls generation. |
| **Settings & Configuration** | `evidenceops.settings` | Read application settings (`Settings`, `get_settings`) for local ports, timeouts, thresholds, and ceilings. | `LiteBridge Composition Root → Settings`<br>(No reverse dependency; core decoupled) | LiteBridge core accepts configuration via typed policies (`RetrievalPolicy`, `BudgetPolicy`). Application settings are wired in composition root (`factory.py`). |
| **Evaluation Identities & Artifacts** | `evidenceops.evaluation.identity`<br>`evidenceops.evaluation.artifacts`<br>`evidenceops.evaluation.contracts` | Reuse deterministic SHA-256 fingerprinting (`generate_file_identity`), run manifest models, and benchmark contracts. | `LiteBridge Eval Adapter → Evaluation Identity`<br>(No reverse dependency) | Ground-truth datasets and benchmarks remain immutable. Evaluated separately through contract tests in Phase L8. |
| **Observability & Tracing** | `evidenceops.observability.tracing` | Reuse `TracingService` and strict `RedactionPolicy` (SHA-256 hashing, zero raw query/text/prompt export). | `LiteBridge Composition Root → Tracing Service`<br>(No reverse dependency; core decoupled) | Telemetry hooks are wired at composition boundaries. Core contracts remain independent of tracing backends. |

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

## G. Architecture Guardrail Amendment: Product Boundary and Portability

### 1. Why Unidirectional Dependency Alone Is Not Enough
The baseline dependency constraint (`LiteBridge → EvidenceOps`, `EvidenceOps ↛ LiteBridge`) protects the stability of EvidenceOps on `main`. However, simple unidirectional dependency is insufficient on its own: without explicit port/adapter boundaries, LiteBridge core code could directly import EvidenceOps domain models, Qdrant store classes, BM25 indices, LangGraph nodes, or API schemas. Doing so would tightly couple LiteBridge to EvidenceOps internals, converting LiteBridge into an EvidenceOps-specific feature folder rather than an independent, portable product.

Therefore, ground truth is explicitly defined as:
> **LiteBridge is the product boundary. EvidenceOps is the first adapter and testbed.**

The required dependency hierarchy is:

```text
LiteBridge core contracts and services
        ↑
LiteBridge adapters
        ↑
EvidenceOps local-retrieval adapter
        ↑
EvidenceOps public services/contracts
```

**Forbidden direction:**
```text
EvidenceOps core → LiteBridge
```

**Also forbidden:**
```text
LiteBridge core → EvidenceOps-specific retrieval models,
                  Qdrant clients,
                  BM25 internals,
                  raw loaders,
                  LangGraph nodes,
                  API routes,
                  dashboard code,
                  generation client internals
```

### 2. Public Contracts Must Be LiteBridge-Owned
All public contracts (`ContextPackage`, `EvidenceRecord`, `RetrievalPolicy`, `GenerationPolicy`, `SourcePolicy`, `BudgetPolicy`) must be defined and owned exclusively by LiteBridge (`src/evidenceops/bridge/contracts.py`). Downstream applications, SDK consumers, and external tools must interact solely with LiteBridge contracts. EvidenceOps-specific classes or types must never appear in public LiteBridge signatures or return values.

### 3. EvidenceOps Is an Adapter, Not the Public SDK
EvidenceOps provides a verified local-first retrieval, sparse/dense indexing, and evidence-verification engine. In LiteBridge, EvidenceOps functions strictly as an underlying retrieval adapter (`adapters/evidenceops_local.py`) and initial local testbed. It does not define LiteBridge's public identity or public API.

### 4. Core, Port, Adapter, and Composition Separation
- **LiteBridge Core (`contracts.py`, `errors.py`, `context_builder.py`, `service.py`):** Owns public contracts, `ContextPackage`, `EvidenceRecord`, policies, budget semantics, evidence ranking and ordering, stable citation identities (`[C1]`, `[C2]`), safe context rendering, reproducibility hashes, public facade, and sanitized error envelopes. The core must contain zero imports of EvidenceOps internal types.
- **LiteBridge Ports (`ports.py`):** Owns provider-neutral protocols such as `EvidenceRetriever`. Returns LiteBridge-neutral candidate records (`RawEvidenceCandidate`). Exposes zero Qdrant, BM25, filesystem, HTTP-client, or provider-client types. Test doubles must be able to satisfy the port without EvidenceOps installed or running.
- **LiteBridge Adapters (`adapters/`):** Translate concrete backend integrations into LiteBridge ports. `adapters/evidenceops_local.py` is the only initial file permitted to import public EvidenceOps services (`LocalDocumentationService`). Future connectors (`WebSearchAdapter`, `WebPageFetcherAdapter`, `StructuredApiAdapter`, `GenerationProviderAdapter`) remain strictly isolated within `adapters/`.
- **Composition Root (`factory.py`):** Wires LiteBridge core with concrete adapters (e.g. `LiteBridge core + EvidenceOps adapter`). Contains wiring logic only, never public business logic.

### 5. Standalone Extraction Gate
LiteBridge may move to an independent package or repository only when all six conditions are met:
1. Public contracts contain zero EvidenceOps-specific classes or types.
2. Core unit tests run using fake ports without running or importing EvidenceOps runtime services.
3. The EvidenceOps adapter passes the identical contract tests as at least one non-EvidenceOps connector.
4. The package can prepare a `ContextPackage` without an LLM provider SDK installed.
5. Public SDK documentation does not require users to understand EvidenceOps.
6. Moving the package requires changing only composition and import wiring, not rewriting core behavior.

Until these conditions are met, `experiment/litebridge-bridge` remains an incubation environment, not a permanently mixed product.

### 6. Generator-Independent `prepare_context()`
`prepare_context()` is strictly generator-independent. It executes retrieval planning, queries configured source adapters via LiteBridge ports, verifies evidence, and packages compact context without importing, configuring, starting, or invoking any generation service or LLM provider SDK. Downstream generation is an optional consumer of `ContextPackage`.

### 7. Adapters, Not Core, Own Backend-Specific Logic
No connector or provider may alter LiteBridge core contracts to accommodate vendor-specific fields, query formats, or credentials. All vendor-specific schemas, API translation, rate-limit policies, and error handling belong strictly inside isolated adapter modules.

### 8. Architecture Rescope Amendment: Snippet-Only Web Retrieval (Phase L3)
Phase L3 provides opt-in, provider-neutral web search snippet retrieval only (initially backed by Tavily Basic Search). Arbitrary direct web page fetching has been intentionally deferred to a future dedicated security-hardening milestone because Python HTTP clients (`httpx`/`httpcore`) lack a stable, version-public mechanism to decouple socket IP connection from TLS SNI validation without accessing private library implementation details. Active Phase L3 contains zero arbitrary outbound URL connection capabilities; its sole external network operation is bounded communication with the configured search provider API endpoint under explicit `ExecutionProfile.HYBRID` opt-in. Phase L4 is eligible only after snippet-only L3 verification passes.


---

## H. Resume Guide

```text
Next approved implementation phase: L1 — Generator-independent context mode.
```

### Updated Phase L1 Implementation Plan (Under Core-Port-Adapter Boundary):
1. Create `src/evidenceops/bridge/` package namespace (deferred until L1 execution).
2. Define LiteBridge-owned runtime Pydantic contracts (`ContextPackage`, `RetrievalPolicy`, `EvidenceRecord`) in `contracts.py`.
3. Define LiteBridge-owned provider-neutral retrieval protocol (`EvidenceRetriever`) and candidate types in `ports.py`.
4. Define sanitized LiteBridge error hierarchy in `errors.py`.
5. Implement isolated `EvidenceOpsLocalRetrieverAdapter` in `adapters/evidenceops_local.py` translating `LocalDocumentationService` results into LiteBridge-neutral candidates.
6. Implement `prepare_context(query, policy)` facade in `service.py` that executes bounded retrieval via `EvidenceRetriever` port and packages evidence into `ContextPackage` without invoking an LLM.
7. Wire default composition in `factory.py`.
8. Implement unit tests and fake-retriever contract tests proving that LiteBridge core executes cleanly without EvidenceOps runtime services or LLM generation calls.
9. Verify that zero LLM generation calls or provider imports occur when invoking `prepare_context()`.

# Architecture & Technical Decision Records (ADR)

## Initial Project Decisions

### ADR-001: Project Scope and Objective
- **Context**: EvidenceOps is created as a comprehensive capstone and hiring portfolio project to demonstrate AI engineering and retrieval systems capabilities.
- **Decision**: Focus on building a testable, cost-aware retrieval and evaluation platform that produces evidence-grounded answers. Avoid treating this as a thesis or claiming novel foundation model architectures.

### ADR-002: Authoritative Technical Source of Truth
- **Context**: Architectural drift and ad-hoc deviations across sub-components can introduce integration failure.
- **Decision**: [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) is the single, authoritative technical source of truth. Any schema, interface, threshold, or scope change must be documented there first.

### ADR-003: Local-First and Zero-Cost Architecture
- **Context**: The project must be fully reproducible without paid cloud subscriptions or remote proprietary APIs.
- **Decision**: Zero paid API calls. Local Ollama for LLM generation, local FastEmbed for dense embeddings, in-process rank-bm25 for sparse retrieval, local Qdrant for vector persistence, and local FlashRank for reranking.

### ADR-004: Text-First Ingestion MVP
- **Context**: Unrestricted web scraping and arbitrary binary parsing can introduce brittle edge cases during early phases.
- **Decision**: MVP focuses on high-value AI engineering markdown and text documentation (Python, FastAPI, LangGraph, Qdrant, Ollama, MCP).

### ADR-005: Bounded Controller Execution
- **Context**: Agent loops can enter infinite or costly retrieval cycles without hard termination conditions.
- **Decision**: Enforce hard limits: Maximum 3 retrieval iterations, maximum 3 retrieval calls, max context limit 24,000 chars, with explicit sufficiency (0.72) and abstention (0.35) thresholds.

### ADR-006: Codex App Superpowers Integration
- **Context**: Superpowers workflows provide test-driven development and planning capabilities within the Codex IDE environment.
- **Decision**: Superpowers is already native in Codex and must not be cloned or duplicated inside the repository.

### ADR-007: Selective ECC (Everything Claude Code) Skills Adoption
- **Context**: External skill repositories may contain Claude-specific hooks, shell scripts, or conflicting instructions.
- **Decision**: Only select, inspect, and vendor Codex-compatible skills into `.agents/skills/` without pulling the full repository.

### ADR-008: Hardware Profile for 8 GB RAM / CPU-First Execution
- **Context**: Host development system has an AMD Ryzen 5 5600G with 8 GB RAM and no discrete CUDA GPU.
- **Decision**: The default local profile is strictly 1.5B to 3B models (`qwen2.5:1.5b` selected and verified for Phase 3). 7B models are strictly optional and must not be configured as default to avoid out-of-memory crashes.

### ADR-009: Ingestion Manifest Contract & Atomic Local Persistence
- **Context**: Ingestion runs require auditability, deterministic traceability, and collision safety without database overhead.
- **Decision**: Persist ingestion manifests as immutable, standalone JSON files named `<manifest_root>/<run_id>.json`. The caller supplies run IDs and timestamps to ensure pure, deterministic serialization (sorted keys, UTF-8, no BOM, trailing newline). Local writes are made atomic via same-directory temporary file writes, `fsync`, and atomic `os.replace`, with default refusal to overwrite existing manifests. Text normalization remains strictly owned by the source loaders, avoiding a redundant normalization subsystem.

### ADR-010: Processed Document Artifacts, Idempotency, and HTML Normalization
- **Context**: Phase 1C indexing needs self-contained access to documents and their pre-computed chunks without re-parsing raw sources. Re-ingesting unchanged sources must avoid redundant writes or duplicate chunk IDs. HTML sources must be supported per SSOT Section 1.2.
- **Decision**: Persist normalized documents and ordered chunks together in atomic, immutable JSON artifacts at `data/processed/<document_id>.json`. `JsonProcessedDocumentStore` checks existing bytes on write; identical files return an `"unchanged"` disposition without writing, while modified contents with the same ID raise `ArtifactConflictError` unless explicit overwrite is enabled. HTML ingestion is handled through standard-library `html.parser.HTMLParser` inside `normalizer.py`, stripping non-content elements and converting headings, paragraphs, lists, and pre/code into clean Markdown-like text for chunking by `MarkdownChunker`.

### ADR-011: Transparent Sparse Index Persistence and Stable Retrieval Ties
- **Decision**: Persist BM25 rebuild inputs, not opaque runtime objects, as deterministic JSON under `data/bm25/`. The snapshot stores canonical chunk/token order plus corpus/configuration SHA-256 fingerprints. Sparse ties use canonical corpus order; RRF ties use best component rank then chunk ID.

### ADR-012: Local Vector Compatibility and Stable Point IDs
- **Decision**: Qdrant points use UUIDv5 derived from `chunk_id`, while payload retains the original ID and allowlisted source metadata. Existing incompatible collections fail rather than being deleted or silently recreated; historical points remain until an explicit future synchronization operation is designed.

### ADR-013: Lazy Model Loading and Non-Calibrated Reranker Scores
- **Context**: In local 8 GB RAM environments, loading FastEmbed and FlashRank ONNX models during import or CLI `--help` consumes memory and adds latency to sparse operations. Additionally, cross-encoder scores must not be conflated with calibrated probabilities or evidence sufficiency.
- **Decision**: FastEmbed and FlashRank providers instantiate model runtimes lazily on first embedding/reranking invocation. CLI commands and sparse searches do not trigger model loading. FlashRank scores are attached to `RetrievalResult.score` and `metadata["rerank_score"]` preserving provenance, and are explicitly documented as uncalibrated query-relative ranking signals rather than sufficiency probabilities.

### ADR-014: STDIO-First Transport and Strict MCP Allowlist
- **Context**: MCP clients (Claude Desktop, IDEs) can communicate over STDIO or network transports. Network transports introduce authentication, port binding, CORS, and remote attack surfaces. Exposing raw filesystem paths or arbitrary internal retrieval parameters introduces prompt-injection and path-traversal vulnerabilities.
- **Decision**: Expose retrieval solely through local STDIO using FastMCP (`evidenceops-mcp`). Reject network transports (SSE/HTTP) in Phase 2. Expose exactly three allowlisted tools (`search_documentation`, `get_document_chunk`, `get_source_metadata`). Validate all inputs with strict Pydantic models forbidding extra fields (`extra="forbid"`). Sanitize IDs against path traversal before disk access. Reuse `DocumentationService` across CLI and MCP to guarantee identical retrieval semantics.

### ADR-015: Bounded LangGraph Orchestration and Grounded Generation (Phase 3 verified)
- **Context**: Autonomous multi-hop agents can loop indefinitely, hallucinate non-existent citation references, or overwhelm CPU/RAM budgets without explicit resource boundaries.
- **Decision**: Orchestration is compiled into a bounded LangGraph `StateGraph` with strict mathematical convergence guarantees:
  1. Maximum 3 retrieval calls and maximum 3 reformulation iterations per query run.
  2. Maximum 24,000 characters packed context and maximum 6 chunks passed to generator.
  3. Strict deterministic heuristic routing: code identifiers -> sparse, complex multi-hop -> hybrid, semantic concepts -> dense.
  4. Non-LLM composite sufficiency ($S = 0.45R + 0.25C + 0.15D + 0.15A$) and conservative pairwise conflict detection before generation.
  5. Deterministic sequential citation assignment (`[C1]`, `[C2]`, ...) with verification: answers citing hallucinated or malformed IDs trigger at most one structured correction retry before explicit abstention (`AbstentionReason.INVALID_CITATIONS`).
  6. Zero paid APIs: native local Ollama running `qwen2.5:1.5b` at `temperature=0.0`.

- **Phase 3 completion amendment (2026-09-05)**: Retain the eleven-node architecture;
  validate canonical Pydantic state on both sides of every node. Explicit guards,
  repeated query-route detection, unchanged-evidence detection and one failure fallback
  bound retrieval; a recursion limit of 64 is only the last-resort guard. Missing
  dependencies are recorded without pretending an actual search occurred.
- **Evidence and conflict policy**: Use the SSOT formula and thresholds 0.72/0.35/0.60.
  Generation additionally requires conflict below 0.30 per SSOT section 5.3. Choose
  the SSOT-permitted immediate abstention on material conflict, preserving chunk IDs
  before reranking can remove witnesses. Compare matching prose subjects and units;
  code examples and typed assignments are not global configuration claims. This is
  a limited heuristic, not semantic contradiction detection or calibrated confidence.
- **Grounding and repair**: Factual generation requires evaluated sufficient packed
  evidence. Only an independently checked greeting with citations disabled may use
  direct generation. Prompts enumerate only packed labels; one correction retains all
  grounding rules. Rejected answers are discarded on abstention. Citation validation
  proves syntax and membership, not entailment of every claim; Phase 4 owns evaluation.
- **CPU and offline query policy**: Native qwen2.5:1.5b, temperature 0, 60-second HTTP
  timeout, default output cap 256 tokens (1..512). Serialize generation per client.
  The query CLI requires cached FastEmbed/FlashRank models; additive offline flags
  retain earlier retrieval acquisition defaults and algorithms. Live smoke uses
  4,000 context characters and two chunks; 24,000/six remain hard default ceilings.
- **Configuration bounds**: In addition to SSOT query ceilings, reject non-finite
  numbers and bound Qdrant timeout to 60 seconds, embedding dimensions to 65,536,
  RRF k to 10,000, source input to 100 MB and simulated unit costs to 1,000 USD/1k.
  These defensive input bounds do not change existing effective retrieval defaults.
  Local service URLs reject credentials, query strings, fragments and non-HTTP schemes.
- **Failure surface**: QueryResponse retains its original fields and adds allowlisted
  audit summaries. Raw exception messages, graph state and backend metadata do not
  cross this boundary. CLI service errors exit nonzero; safe policy abstentions are
  distinct from service failures. No MCP contract, SSOT or Phase 4 implementation changed.

### ADR-016: Evaluation Benchmark Design, Layer B Alignment, and Split Isolation
- **Context**: Public RAG benchmarks (HotpotQA, MS MARCO, BEIR) exhibit severe Layer B mismatches (missing original documents, differing chunk boundaries, and external web domain assumptions).
- **Decision**: Construct a controlled 100-sample benchmark dataset (`evidenceops-controlled-v1.json`) grounded directly in the verified ingested corpus chunks. Partition strictly into 60 DEV, 20 VAL, and 20 TEST splits across five question archetypes: 30 single-fact, 25 multi-hop, 20 contrastive, 10 temporal-ambiguous, and 15 unanswerable. Generate canonical JSON SHA-256 identity (`evidenceops-controlled-v1.identity.json`) and dataset provenance metadata. The `OracleSupervisor` is programmatically restricted to the DEV split only; any attempt to evaluate or train on VAL or TEST raises an immediate `ValueError` to prevent data leakage.

### ADR-017: Fair Baseline Benchmarking and Equal Budget Constraints
- **Context**: Comparing adaptive agentic RAG against artificially weakened baselines produces misleading evaluation claims.
- **Decision**: Baseline systems (`NaiveDenseRAG`, `BM25RAG`, `TwoStepHybrid`) and EvidenceOps share identical context ceilings (top-k=5..6, max 24,000 characters), identical prompt formatting templates, identical generator backend (`qwen2.5:1.5b` via local Ollama), identical temperature (0.0), and identical citation verification rules. All systems implement the `BaseRAGSystem` abstract protocol.

### ADR-018: Controller Training Pipeline and Heuristic Fallback Guardrails
- **Context**: Learned routing policies can overfit, fail on edge cases, or behave unpredictably outside the training distribution.
- **Decision**: Implement `ControllerTrainingPipeline` with deterministic 10-feature state extraction (budget counters, conflict scores, sufficiency states, and token/syntax features) and a multi-class `LogisticRegression` classifier trained strictly on DEV split supervision. `LearnedRetrievalController` enforces hard iteration/retrieval budget guardrails and transparently falls back to `HeuristicRetrievalController` if model confidence is below 0.50 or if the model artifact is unavailable.

### ADR-019: Paired Bootstrap Statistical Significance and Reproducible Run Manifests
- **Context**: RAG evaluation metrics fluctuate across test sets; reporting raw mean score improvements without confidence intervals or statistical testing violates empirical rigor.
- **Decision**: Implement non-parametric paired bootstrap testing (default 500-1,000 resamples, 95% bootstrap confidence intervals, and two-tailed p-values with alpha=0.05). Benchmark runs emit standalone, immutable directories under `eval/runs/<run_id>/` containing a machine-readable `manifest.json` (per-sample scores, system aggregates, environment profile, and bootstrap comparisons) and a GitHub-flavored markdown `leaderboard.md`.

### ADR-020: Strict Observability Redaction and Local OpenTelemetry Tracing
- **Context**: Telemetry is required for local profiling and Jaeger tracing, but raw queries, prompts, generated answers, or corpus chunks must never be emitted into spans or logs.
- **Decision**: Local OpenTelemetry tracing exports to local Jaeger (`http://localhost:4318/v1/traces`) with zero-dependency socket availability pre-flight to eliminate connection retry spam when Jaeger is offline. A strict `RedactionPolicy` computes SHA-256 hashes and token counts for queries, answers, and chunk text, guaranteeing that no raw text crosses into span attributes or span events. LangGraph orchestration nodes are transparently instrumented at the `validated_node` boundary.

### ADR-021: Local FastAPI Service, Observability Dashboard, and Bounded Concurrency
- **Context**: Demonstrating the platform to technical recruiters and evaluators requires an interactive interface and HTTP API without violating the zero-cloud, local-first, 8 GB RAM constraints or introducing external attack surfaces.
- **Decision**: Implement a local-first FastAPI service (`create_app`) and same-origin dashboard (`/`, `/static/`) with zero external CDNs, external web fonts, or npm dependencies. Restrict host binding strictly to loopback (`127.0.0.1`). Enforce bounded CPU/RAM concurrency via `asyncio.Semaphore` (`api_max_concurrent_queries=1`, `api_max_concurrent_evaluations=1`), offload synchronous orchestration/generation to worker threads (`asyncio.to_thread`), and cap in-memory run history to 100 entries. API error responses use a standardized sanitized envelope (`code`, `message`, `details`) with complete redaction of tracebacks, local file paths, and backend exceptions. The evaluation endpoint (`POST /v1/eval/run`) strictly validates against allowlisted datasets and systems, spawning a daemon thread that outputs solely to bounded relative artifact paths (`eval/runs/<run_id>/`). All frontend DOM updates enforce strict `.textContent` and attribute-level escaping to guarantee complete XSS protection.

### ADR-022: One-Click Desktop Lifecycle Automation and Resource Reclaim
- **Context**: Running multi-service local AI applications requires orchestrating Docker, Ollama, and FastAPI, and manual process management risks persistent memory and VRAM hogging after the user finishes.
- **Decision**: Provide automated one-click launcher scripts (`scripts/run_app.ps1` and `EvidenceOps.bat`) that sequentially verify and start Docker Qdrant, Ollama, and FastAPI, poll the health readiness probe, and open the dashboard in dedicated browser app mode (`--app=...`). When the application window is closed, the launcher traps exit in a `finally` block to immediately terminate the backend process, stop the Qdrant container, and issue an explicit `ollama stop` command to fully unload model weights and reclaim 100% of host RAM.

### ADR-023: Phase 6 Release Hardening, Recruiter Trajectory UX, and Deterministic Smoke Suite
- **Context**: In Phase 6, the system transitions from verified functional components to a hardened, reproducible, portfolio-ready release. Recruiter evaluation requires clear visual explanation of adaptive retrieval decisions without weakening security, compromising the 8 GB CPU-safe profile, or leaking ungrounded claims.
- **Decision**:
  1. **Recruiter-Facing Visual Trajectory UX**: Enhance the same-origin dashboard with an interactive, chronological 5-stage pipeline trajectory (Query Analysis -> Controller Action -> Retrieval -> Sufficiency/Conflict Verification -> Grounded Generation / Abstention) rendered using safe DOM APIs (`textContent`, `createElement`, `replaceChildren`) with zero `.innerHTML`, zero external CDNs, and zero third-party font dependencies. Add interactive sample queries representative of the processed documentation corpus and collapsible evidence excerpt cards.
  2. **Strict Offline Model Isolation**: Enforce `local_models_only=True` in both runtime API and evaluation factory to eliminate unauthenticated Hugging Face download attempts and ensure offline resilience.
  3. **Deterministic 7-Case Smoke Suite**: Introduce `tests/unit/api/test_phase6_smoke.py` validating the seven operational query invariants (direct answer gate, exact identifier sparse retrieval, semantic documentation search, multi-hop bounded retrieval, clean abstention on unsupported facts, sanitized dependency failure mapping, and concurrency serialization) without requiring live LLM inference.
  4. **Empirical Rigor and Claim Qualification**: All portfolio documentation explicitly preserves human-review status as `pending` (pending expert clinical/domain review) and notes statistical limitations of the 20-item held-out test split, rejecting simulated cost claims or fabricated metrics.

### ADR-024: Local Generation Provider Abstraction and Evaluation Fact-Family Split Integrity
- **Context**: EvidenceOps previously tied its runtime directly to Ollama. While Ollama remains the default local-first engine, tying the architecture permanently to one executable risks coupling. Additionally, evaluation rigor requires eliminating cross-split data leakage where questions testing identical underlying facts or close paraphrases cross between development and test splits.
- **Decision**:
  1. **Framework-Independent Local Provider Boundary**: Introduced `GenerationProvider` protocol and `create_generation_provider` factory. Ollama (`OllamaGenerationProvider`) remains the verified default running `qwen2.5:1.5b`. Added `OpenAICompatibleLocalProvider` strictly restricted to local loopback HTTP endpoints (`127.0.0.1` or `localhost`, e.g. LM Studio or vLLM). It strictly rejects external IPs, public hostnames, HTTPS, user-supplied endpoints in API requests, and API keys.
  2. **Fact-Family Split Integrity**: Augmented `EvaluationSample` with a machine-readable `fact_family_id` field. Re-partitioned the frozen 100-item controlled benchmark (`evidenceops-controlled-v1.json`) across 52 distinct fact families so that 100% of variants testing the same atomic fact belong to one split only (60 dev / 20 val / 20 test). Cross-split leakage is strictly prohibited by `validate_evaluation_dataset`.
  3. **Controller Benchmark Comparison**: Learned controller trained strictly on the dev split achieves 20/20 (100%) initial routing agreement on the held-out test split, confirming policy parity. In accordance with empirical rigor, the heuristic controller is retained as the production default, and no superior generalization is claimed from the 20-item test split. Human review remains formally marked as pending.

### ADR-025: LiteBridge Phase L0 Branch and Architecture Baseline
- **Context**: LiteBridge is designed as an experimental, model-agnostic retrieval and context-preparation middleware layer that reuses EvidenceOps's verified local retrieval, evidence validation, and provider contracts. Developing this capability must not destabilize the verified Phase 6 EvidenceOps baseline, create architectural drift, or introduce premature external network dependencies.
- **Decision**:
  1. **Branch-First Isolation**: All LiteBridge experimentation is strictly isolated on branch `experiment/litebridge-bridge`. The `main` branch remains the stable, protected EvidenceOps production baseline.
  2. **In-Repository Additive Placement**: LiteBridge is initially housed inside this repository under `src/evidenceops/bridge/` (to be created in Phase L1), preventing dual-repository overhead while interfaces stabilize.
  3. **Strict Unidirectional Dependency Direction**: The dependency rule is strictly `LiteBridge → stable EvidenceOps public services/contracts`. EvidenceOps core modules (`ingestion`, `retrieval`, `evidence`, `generation`, `graph`, `api`, `mcp_server`, `cli`, `dashboard`) must never import or depend on LiteBridge.
  4. **Local-Only Default Profile**: Phase L0 defaults to `local_only` (zero outbound web requests, zero external LLM adapters, zero credentials). External providers require explicit opt-in configuration in future phases. Private evidence must never silently fall back to an external provider.
  5. **No Runtime Scaffolding in L0**: L0 is documentation-first. Public contracts are defined at the design level in `docs/architecture/LiteBridge_L0_Architecture_Baseline.md` and `LiteBridge_SSOT.md`. No runtime code, empty package scaffolds, web clients, or provider adapters are created in L0. LiteBridge is not yet model-agnostic at runtime; it is only architecturally chartered for that outcome.
  6. **Criteria for Standalone Repository Extraction**: Eventual extraction to an independent repository requires meeting four preconditions:
     - Public contracts (`ContextPackage`, `RetrievalPolicy`, `GenerationPolicy`, `SourcePolicy`, `BudgetPolicy`) are stabilized and versioned.
     - Independent package lifecycle and versioning are established without breaking EvidenceOps.
     - Multiple consumer applications or frameworks are identified and verified.
     - Complete decoupling from EvidenceOps internal data stores (operating solely over public abstract protocols).

### ADR-026: LiteBridge Core-Port-Adapter Boundary and Future Extraction Policy
- **Context**: In Phase L0 (ADR-025), LiteBridge established a branch-first isolation and unidirectional dependency (`LiteBridge → EvidenceOps`). However, unidirectional dependency alone does not prevent LiteBridge core code from directly importing and coupling to EvidenceOps domain models, Qdrant clients, BM25 indices, LangGraph nodes, or API schemas. If LiteBridge core imports these concrete types directly, LiteBridge becomes an EvidenceOps-specific internal feature folder rather than a portable, extractable retrieval-planning and context-preparation product.
- **Decision**:
  1. **Product Boundary Ground Truth**: Explicitly declare that **LiteBridge is the product boundary; EvidenceOps is the first adapter and testbed**.
  2. **Strict Inverted Dependency Hierarchy**:
     ```text
     LiteBridge core contracts and services
             ↑
     LiteBridge adapters
             ↑
     EvidenceOps local-retrieval adapter
             ↑
     EvidenceOps public services/contracts
     ```
     - Forbidden direction: `EvidenceOps core → LiteBridge`.
     - Also forbidden: `LiteBridge core → EvidenceOps-specific retrieval models, Qdrant clients, BM25 internals, raw loaders, LangGraph nodes, API routes, dashboard code, generation client internals`.
     - Only an isolated adapter module (`adapters/evidenceops_local.py`) may import verified public EvidenceOps interfaces (`LocalDocumentationService`).
  3. **Core, Port, and Adapter Architectural Separation**:
     - **LiteBridge Core**: Owns public contracts (`ContextPackage`, `EvidenceRecord`, policies, budget semantics), evidence ordering, citation identity (`[C1]`, `[C2]`), safe context rendering, reproducibility identity, public facade (`prepare_context()`, `answer()`), and sanitized errors. Contains zero imports of EvidenceOps internal types.
     - **LiteBridge Ports**: Owns narrow provider-neutral protocols (e.g. `EvidenceRetriever`) returning LiteBridge-neutral candidate records (`RawEvidenceCandidate`). Exposes zero backend-specific, framework-specific, or client-specific objects. Fully testable via lightweight doubles without EvidenceOps installed or running.
     - **LiteBridge Adapters**: Translates concrete backend integrations into LiteBridge ports. Only adapters and factories may import integration-specific code or vendor SDKs.
     - **Composition Root**: Wires core services with adapters (`factory.py`).
  4. **Why LiteBridge Cannot Expose EvidenceOps Types**: Exposing EvidenceOps types in LiteBridge's public contracts would permanently couple downstream users, SDK consumers, and LLM applications to EvidenceOps, defeating LiteBridge's purpose as a reusable, model-agnostic context middleware product.
  5. **Why EvidenceOps Remains First Adapter & Testbed**: EvidenceOps provides an existing, verified local-first retrieval, sparse/dense indexing, and citation-validation pipeline that serves as an ideal zero-cloud reference implementation and testbed for LiteBridge without requiring paid APIs or remote services.
  6. **Consequences & Accepted Trade-Off**: Writing an explicit adapter layer introduces a small translation boundary between EvidenceOps and LiteBridge ports, but guarantees complete independence of core logic, unblocks future extraction, and ensures testability without heavy runtime services.
  7. **Rejected Alternative**: Directly importing EvidenceOps services across LiteBridge core without an adapter layer. Rejected because it permanently entangles LiteBridge with EvidenceOps schemas, Qdrant/BM25 internals, and application runtime semantics.
  8. **Standalone Extraction Gate (Six Mandatory Preconditions)**:
     - Public contracts contain no EvidenceOps-specific classes or types.
     - Core unit tests run using fake ports without running or importing EvidenceOps runtime services.
     - The EvidenceOps adapter passes the identical contract tests as at least one non-EvidenceOps connector.
     - The package can prepare a `ContextPackage` without a provider SDK installed.
     - Public SDK documentation does not require users to understand EvidenceOps.
     - Moving the package requires changing only composition/import wiring, not rewriting core behavior.
  9. **No Runtime Implementation**: This ADR is documentation and architecture governance prior to Phase L1; no implementation code, tests, dependencies, or configuration are modified in this task.

### ADR-027: LiteBridge Phase L1 Generator-Independent Context Mode
- **Context**: Phase L1 implements the core, generator-independent context-preparation layer (`prepare_context()`). The implementation must adhere strictly to the Core-Port-Adapter boundary established in ADR-026 and `LiteBridge_SSOT.md` (v1.1), ensuring that LiteBridge core remains portable and decoupled from EvidenceOps models and LLM generation providers.
- **Decision**:
  1. **Primary Product Boundary**: `ContextPackage` is the primary public output of LiteBridge. Downstream LLM applications consume this immutable package. Generation is optional and separated from context preparation.
  2. **Strict Generator Independence**: `prepare_context()` contains zero imports, zero configuration, and zero calls to any LLM generation provider or LangGraph orchestration node. Calling `prepare_context()` executes retrieval and context packaging only.
  3. **Port-Based Local Retrieval**: Core `LiteBridge` service depends exclusively on the `EvidenceRetriever` protocol (`ports.py`). Retrieval is executed via a single bounded call per request.
  4. **Isolated EvidenceOps Adapter**: `EvidenceOpsLocalRetrieverAdapter` (`adapters/evidenceops_local.py`) is the sole module permitted to import EvidenceOps retrieval services (`LocalDocumentationService`). It translates `DocumentationSearchResult` into LiteBridge-neutral `RawEvidenceCandidate` tuples.
  5. **Composition Boundary**: `build_litebridge()` (`factory.py`) wires the adapter into LiteBridge with neutral reproducibility identifiers (`adapter_id`, `corpus_identity`, `index_identity`, `code_identity`) without exposing Qdrant/BM25 internals.
  6. **True Contract Immutability**: All public contracts (`ContextPackage`, `EvidenceRecord`, `RetrievalPolicy`, `RawEvidenceCandidate`, `RetrievalBatch`) enforce `frozen=True`, `extra="forbid"`, and use immutable `tuple` collections instead of mutable lists or dicts.
  7. **Whole-Item Extractive Budget Enforcement**: Evidence items are selected in retrieval rank order and included only if the entire item fits within character and token budgets (evaluated against the final rendered `context_text` including headers and citation markers). Items are never silently truncated in the middle. Stop reason reflects precedence: `NO_EVIDENCE` if 0 candidates returned; `BUDGET_EXCEEDED` if candidates returned but none or only some fit; `SUCCESS` if all candidates fit.
  8. **Deterministic Package Identity**: `package_id` is derived strictly from stable inputs (normalized query hash, policy, selected evidence IDs, reproducibility metadata) and strictly excludes non-deterministic execution timings or timestamps.
  9. **Single-Inheritance Error Hierarchy**: All LiteBridge errors inherit strictly from `LiteBridgeError(Exception)` without multiple-inheritance complexities. Underlying causes are preserved via `__cause__` while keeping public representations sanitized.
  10. **Deferred Capabilities**: Web search, external page fetching, external LLM adapters, context compression, and API/MCP tools remain strictly deferred to subsequent phases.

### ADR-028: LiteBridge Phase L2 Source Registry and Private Local Source Policy
- **Context**: Phase L2 extends LiteBridge with source-registry and source-selection capabilities so that LiteBridge can safely identify, configure, and select registered document sources while preserving the generator-independent Core-Port-Adapter boundary established in L0/L1.
- **Decision**:
  1. **Source Agnostic Core Boundary**: LiteBridge core owns the public domain contracts `SourceDescriptor`, `SourcePolicy`, `PrivacyClassification`, `SourceFreshness`, and the operational `SourceRegistry`. Core has zero imports of EvidenceOps models, Qdrant/BM25 internals, database drivers, or LLM generation providers.
  2. **Allowlist-Based In-Memory Source Registry**: Sources are registered in-memory via `SourceDescriptor` and `EvidenceRetriever`. Sources cannot be arbitrary user-supplied filesystem paths, URLs, database connection strings, or raw queries.
  3. **Strict Single-Source Selection in L2**: Exactly one local source is resolved per `prepare_context()` call:
     - Empty `SourcePolicy` or `None` resolves the deterministic registered default source (`evidenceops_local_docs`).
     - A single allowed source ID in `SourcePolicy` resolves that registered source if enabled.
     - Specifying more than one source ID is rejected prior to retrieval with `LiteBridgeValidationError`.
     - Specifying an unknown or disabled source raises `LiteBridgeSourceError` prior to retrieval.
     - No multi-source fan-out, planning, or evidence fusion is performed in L2.
  4. **Direct-Retriever Compatibility**: `LiteBridge(retriever=...)` remains supported for backward compatibility and testing. Direct-retriever mode permits `source_policy=None` or empty `SourcePolicy()`; specifying an explicit source ID in direct-retriever mode raises `LiteBridgeSourceError`.
  5. **Required Provenance Identity**: `source_id: str` is required (with no fake public defaults) on `RawEvidenceCandidate` and `EvidenceRecord`. Returned candidate `source_id` is validated against the resolved source ID (mismatches raise `LiteBridgeRetrievalError`).
  6. **Core-Guaranteed Reproducibility Integrity**: Core-resolved `source_id` and `adapter_id` metadata take precedence and cannot be overwritten by adapter-provided reproducibility metadata. `ContextPackage.package_id` deterministically incorporates `source_id` and excludes timing values.
  7. **Declarative Timeout and Zero Retries**: `timeout_ms` and `max_retries=0` are declarative contract properties. If an upstream service raises `TimeoutError`, it is mapped to a sanitized `LiteBridgeTimeoutError` without unsafe thread cancellation, process termination, or retries. Existing `LiteBridgeTimeoutError` instances pass through unwrapped.
  8. **Deferred Capabilities**: Multi-source planning/fusion (Phase L4), web search and page retrieval (Phase L3), hosted/hybrid execution profiles, and LLM answer generation remain strictly out of scope.

### ADR-029: LiteBridge Phase L3 Safe Web Search and Page Retrieval
- **Context**: Phase L3 implements an optional, opt-in web search and safe page-retrieval capability. The default LiteBridge behavior must remain fully local and generator-independent with zero paid API keys, zero network calls, and zero external dependencies required. Web retrieval introduces external attack surfaces (SSRF, data leakage, unbounded latency, rate limits), requiring strict defense-in-depth boundaries.
- **Decision**:
  1. **Default Local-Only Invariant**: Default `build_litebridge()` operates 100% locally with zero network calls, zero API keys required, and no web source registered.
  2. **Strict Opt-In Web Retrieval Guardrails**: Web retrieval is activated only when all 5 conditions are simultaneously satisfied:
     - `ExecutionProfile.HYBRID` requested;
     - `tavily_web_search` source explicitly selected in `SourcePolicy`;
     - `WebRetrievalPolicy(allow_external_query=True, ...)` provided;
     - `LITEBRIDGE_ENABLE_TAVILY_WEB=true` configured in settings;
     - `TAVILY_API_KEY` present and non-blank in factory composition.
     If any condition is missing, web retrieval is rejected before any network call.
  3. **Core-Port-Adapter Decoupling**: Core modules (`contracts.py`, `ports.py`, `errors.py`, `service.py`, `context_builder.py`, `source_registry.py`) contain zero imports of `httpx`, `requests`, `urllib`, `socket`, `ipaddress`, EvidenceOps internals, or LLM providers. All networking, HTTP transport, and SSRF controls are isolated in `adapters/`.
  4. **Strict SSRF Protection in Page Fetcher**: `SafeWebFetcher` enforces HTTPS-only, no credentials, default port 443 only, no URL fragments, and no IP literals. Pre-request DNS resolution asserts that all resolved IP addresses are globally routable, rejecting private, loopback, link-local, multicast, and reserved addresses.
  5. **Strict Domain Allowlist**: Domain entries in `LITEBRIDGE_WEB_ALLOWED_FETCH_DOMAINS` are parsed once into lowercase, trimmed, deduplicated exact hostnames. Wildcards, URLs, ports, IPs, and empty entries are rejected. An empty allowlist safely disables page fetching while preserving search snippets.
  6. **Manual Hop Redirect Validation**: `SafeWebFetcher` operates with `follow_redirects=False` and `trust_env=False`. Each redirect hop (max 3) is independently validated against SSRF and allowlist rules before issuing the next request.
  7. **Policy-to-Settings Clamping**: `WebRetrieverAdapter` clamps caller-requested web limits against configured maximums:
     `effective_results = min(policy.web.max_search_results, settings.litebridge_web_max_results)`
     `effective_page_fetches = min(policy.web.max_page_fetches, settings.litebridge_web_max_page_fetches)`
     A caller can never increase configured resource limits.
  8. **Candidate Source-Kind Validation**: `service.py` validates candidate source kinds against the source descriptor: local document descriptors permit only `LOCAL_DOCUMENT`; web search descriptors permit both `WEB_SEARCH_SNIPPET` and `WEB_PAGE_EXCERPT`.
  9. **Bounded In-Memory TTL Caching**: `WebRetrievalCache` caches query/policy batches with bounded LRU eviction and TTL. Cache hits return candidates with `web_calls=0`.
  10. **Package ID Determinism**: `package_id` deterministically incorporates `canonical_url` and `content_hash` of selected web evidence, but strictly excludes `fetched_at_utc`, network timings, and cache status.
  11. **Deferred Capabilities**: Multi-source planning/fusion (Phase L4), external provider LLM adapters (Phase L5), and compression remain strictly deferred.

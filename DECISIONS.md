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
- **Decision**: The default local profile is strictly 1.5B to 3B models (`qwen2.5:3b-instruct`). 7B models are strictly optional and must not be configured as default to avoid out-of-memory crashes.

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

### ADR-015: Bounded LangGraph Orchestration and Grounded Generation (Early Implementation)
- **Context**: Autonomous multi-hop agents can loop indefinitely, hallucinate non-existent citation references, or overwhelm CPU/RAM budgets without explicit resource boundaries.
- **Decision**: Orchestration is compiled into a bounded LangGraph `StateGraph` with strict mathematical convergence guarantees:
  1. Maximum 3 retrieval calls and maximum 3 reformulation iterations per query run.
  2. Maximum 24,000 characters packed context and maximum 6 chunks passed to generator.
  3. Strict deterministic heuristic routing: code identifiers -> sparse, complex multi-hop -> hybrid, semantic concepts -> dense.
  4. Non-LLM composite sufficiency ($S = 0.45R + 0.25C + 0.15D + 0.15A$) and conservative pairwise conflict detection before generation.
  5. Deterministic sequential citation assignment (`[C1]`, `[C2]`, ...) with verification: answers citing hallucinated or malformed IDs trigger at most one structured correction retry before explicit abstention (`AbstentionReason.INVALID_CITATIONS`).
  6. Zero paid APIs: local Ollama running `qwen2.5:3b-instruct` (or compatible small models) at `temperature=0.0`.

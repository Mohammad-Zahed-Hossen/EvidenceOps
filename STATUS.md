# Project Status

## Current Status: Phase 2 (MCP Foundation) Complete; Phase 3 Orchestration Early Implementation Preserved

Phase 0, Phase 1A, Phase 1B, Phase 1C, and Phase 2 (MCP Foundation) are complete. In addition, Phase 3 (LangGraph Orchestration & Grounded Generation) has been implemented early and is preserved.

Corpus scope provisionally approved after acquisition; provenance and reproducibility corrections required before final acceptance. The Phase 1C manual 30-question retrieval inspection judgments remain pending human review; no unmeasured retrieval-quality improvements are claimed.

Full test suite: 253 passed, 3 skipped, 89.8% statement coverage.

## Phase Roadmap & Status

- [X] **Phase 0: Environment and repository preflight** (Completed)
- [X] **Phase 1A: Domain contracts and configuration** (Completed)
- [X] **Phase 1B: Ingestion and chunking** (Completed in full)
- [X] **Phase 1C: Local retrieval subsystem** (Completed in full; human judgment gate pending)
  - Deterministic BM25 sparse retrieval, code-aware tokenizer, FastEmbed dense retrieval, local Qdrant vector store, hybrid RRF (`k=60`), FlashRank reranking.
  - *Corpus status*: Corpus scope provisionally approved after acquisition; provenance and reproducibility corrections required before final acceptance. 30-question inspection judgments pending final review.
- [X] **Phase 2: MCP Foundation** (Completed in full)
  - **Shared Documentation Service**: `LocalDocumentationService` providing unified abstraction over sparse, dense, and hybrid retrieval with reranking, chunk retrieval, and document provenance metadata. Shared seamlessly between retrieval CLI and MCP server.
  - **Three Approved Tools**: Exactly three allowlisted tools exposed: `search_documentation`, `get_document_chunk`, and `get_source_metadata`. All tools enforce strict Pydantic schemas with `extra="forbid"` and bounded parameters (`top_k` 1..20, `mode` enum: sparse/dense/hybrid).
  - **STDIO-Only Server**: FastMCP server running strictly over local STDIO via entry point `evidenceops-mcp` (`src/evidenceops/mcp_server/__main__.py`). Network transports (SSE/HTTP) are strictly excluded.
  - **Security & Path Traversal Guardrails**: Validates all IDs against `^[a-zA-Z0-9_-]+$` before accessing disk; rejects unrecognized parameters without leaking paths or internals.
  - **Verification**: Contract tests verify exact 3-tool schema, bounded parameters, input validation, and live STDIO JSON-RPC handshake.
- [X] **Phase 3: LangGraph Orchestration & Grounded Generation** (Early Implementation Completed)
  - *Note*: Implemented ahead of schedule; preserved for Phase 3 evaluation and validation.
  - **State & Guardrails**: Pydantic `EvidenceOpsState` enforcing max 3 retrieval iterations, max 3 calls, 24k char limit, and `AbstentionReason` enum.
  - **Heuristic Controller**: `RegexFeatureExtractor` and `HeuristicRetrievalController` for deterministic routing without prompt latency.
  - **Evidence Context & Sufficiency**: Deduplicating adapter, citation mapper, bounded context packer (top 6 chunks, untrusted boundary tags), composite sufficiency scoring ($S = 0.45R + 0.25C + 0.15D + 0.15A$), and conservative pairwise conflict detection.
  - **Ollama Client & Citations**: Local `OllamaClient` targeting `/v1/chat/completions` at `temperature=0.0`, strict prompt builders, inline citation validator, and query reformulator.
  - **Workflow & CLI**: Compiled `StateGraph` with cycle bounding, `QueryService` facade, and `evidenceops-query` command.
- [ ] **Phase 4: Evaluation, Benchmarking & Observability**
  - Ground truth benchmark datasets, retrieval & generation evaluation metrics, OpenTelemetry and Jaeger tracing.
- [ ] **Phase 5: FastAPI Backend & Dashboard**
  - FastAPI backend routes and local Next.js web dashboard.
- [ ] **Phase 6: Hardening and Portfolio Release**
  - End-to-end integration tests, CPU profile optimization, release packaging.

## Current Environment & Non-Blockers

- **Docker daemon**: Reachable; `hello-world` image was not pulled to avoid network/cache side-effects during preflight.
- **Ollama**: Local REST service verified at `http://127.0.0.1:11434`. Local model weights to be pulled during Phase 3 verification.
- **Python / uv**: `uv run python` uses Python 3.12.13 in `.venv`.
- **Hardware Profile (8 GB RAM)**: Strictly CPU-safe with 1.5B to 3B instruct models. 7B models are not default.

## Next Action

- Await human review and sign-off on the Phase 1C 30-question retrieval inspection judgments, then proceed to model pulling and Phase 3 generation evaluation.

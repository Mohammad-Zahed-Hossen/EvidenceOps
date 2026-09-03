# Project Status

## Current Status: Phase 0 (Environment and Repository Preflight) Complete

Repository and local-environment readiness have been verified for Phase 0 preflight. No application features, model weights, Docker Compose stack, ingestion, retrieval, orchestration, API, dashboard, MCP behavior, or evaluation logic has been initiated.

The preflight evidence is recorded in [docs/implementation-readiness.md](docs/implementation-readiness.md) and [docs/setup/initial-setup-report.md](docs/setup/initial-setup-report.md).

## Phase Roadmap & Status

- [x] **Phase 0: Environment and repository preflight** (Completed)
  - Preflight checks for tools, Git, virtual environment, and directory layout.
  - Root `EvidenceOps_SSOT.md` verified as canonical single source of truth.
  - Initial configuration templates, `.gitignore`, and documentation created.
- [ ] **Phase 1A: Domain contracts and configuration** (Pending next action)
  - Domain enums and Pydantic v2 data models (`DocumentRecord`, `ChunkRecord`, `RetrievalAction`, `QueryIntent`, `EvidenceRecord`, `AnswerRecord`, `RunTrace`).
  - Configuration loader (`src/evidenceops/settings.py` via `pydantic-settings`).
  - Structured error types and basic structured logging interface (`src/evidenceops/logging.py`).
  - Focused unit tests for domain contracts (`tests/unit/test_domain_models.py`).
- [ ] **Phase 1B: Ingestion and chunking**
  - Text and markdown document loaders.
  - Document normalizer and chunker with deterministic chunk ID generation.
  - Ingestion pipeline and document manifests.
- [ ] **Phase 1C: BM25 and dense indexes**
  - In-process `rank-bm25` sparse index builder and search.
  - FastEmbed dense vector embeddings.
  - Local Qdrant integration and storage.
  - Reciprocal Rank Fusion (RRF) hybrid search and FlashRank reranking.
- [ ] **Phase 2: LangGraph orchestration**
  - State definition, nodes, transitions, and bounded retrieval cycles (max 3 iterations / calls).
- [ ] **Phase 3: Heuristic controller**
  - Rule-based query routing, evidence sufficiency checks, and abstention logic.
- [ ] **Phase 4: Learned controller**
  - Feature extraction, lightweight classifier/policy, and controller evaluation.
- [ ] **Phase 5: Evaluation and observability**
  - OpenTelemetry and Jaeger tracing integration.
  - Benchmark datasets, evaluation harness, scoring metrics (retrieval & answer grounding).
- [ ] **Phase 6: FastAPI and dashboard**
  - FastAPI backend routes (query, evaluation, metrics).
  - Next.js local dashboard.
  - MCP server integration.
- [ ] **Phase 7: Hardening and portfolio release**
  - End-to-end integration tests, CPU profile optimization, release packaging.

## Current Environment & Non-Blockers

- **Docker daemon**: Reachable; `hello-world` image was not pulled to avoid network/cache side-effects during preflight.
- **Ollama**: Local REST service verified at `http://127.0.0.1:11434`. No model weights pulled yet.
- **Python / uv**: `uv run python` uses Python 3.12.13 in `.venv`.
- **Hardware Profile (8 GB RAM)**: Strictly CPU-safe with 1.5B to 3B instruct models. 7B models are not default.

## Next Smallest Action

- Audit ECC skills (`python-testing` and `verification-loop`) against Superpowers workflow.
- Execute baseline Git commit.
- Dispatch Phase 1A scope to Codex for domain contracts and configuration implementation.

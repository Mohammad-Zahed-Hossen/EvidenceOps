# Project Status

## Current Status: Phase 1B.1 (Single-File Local Loader) Complete

Phase 0, Phase 1A, and Phase 1B.1 are complete. Phase 1B.1 adds only a deterministic, single-file local UTF-8 text/Markdown loader with an allowed-root validation boundary. No chunking, index, model, Docker Compose, API, dashboard, MCP, or evaluation behavior has been implemented.

The preflight evidence is recorded in [docs/implementation-readiness.md](docs/implementation-readiness.md) and [docs/setup/initial-setup-report.md](docs/setup/initial-setup-report.md).

## Phase Roadmap & Status

- [x] **Phase 0: Environment and repository preflight** (Completed)
  - Preflight checks for tools, Git, virtual environment, and directory layout.
  - Root `EvidenceOps_SSOT.md` verified as canonical single source of truth.
  - Initial configuration templates, `.gitignore`, and documentation created.
- [x] **Phase 1A: Domain contracts and configuration** (Completed)
  - Domain enums and Pydantic v2 data models (`DocumentRecord`, `ChunkRecord`, `RetrievalAction`, `QueryIntent`, `EvidenceRecord`, `AnswerRecord`, `RunTrace`).
  - Configuration loader (`src/evidenceops/settings.py` via `pydantic-settings`).
  - Structured error types and basic structured logging interface (`src/evidenceops/logging.py`).
  - Focused unit tests for domain/state, settings, errors, and logging.
  - Verified on 2026-09-04: 17 pytest tests passed; `ruff check src tests`, `ruff format --check src tests`, and `mypy src/evidenceops` passed.
- [x] **Phase 1B.1: Single-file local text and Markdown loader** (Completed)
  - Supports exactly one `.md`, `.markdown`, or `.txt` file per call within an injected allowed root.
  - Enforces path containment, regular-file, size, extension, UTF-8, and non-empty-content validation.
  - Produces deterministic `DocumentRecord` IDs, project-relative URIs, normalized LF text, hashes, and safe metadata.
  - Verified on 2026-09-04: 13 focused loader tests passed and 1 symlink-escape test was skipped because Windows symlink creation lacks the required privilege; full suite: 30 passed, 1 skipped. Ruff, formatting, and mypy passed.
- [ ] **Phase 1B.2: Structure-aware Markdown chunking**
  - Heading-aware chunking with deterministic chunk IDs and no code-fence splits.
- [ ] **Phase 1B: Ingestion and chunking (remaining work)**
  - Text and markdown document loaders.
  - Document normalizer and manifests after explicit authorization.
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

- On explicit authorization, begin Phase 1B.2 by writing failing tests for structure-aware Markdown chunking, including heading preservation and fenced-code boundaries; do not add BM25 or Qdrant work.

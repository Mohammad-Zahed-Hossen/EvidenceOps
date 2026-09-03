# Project Status

## Current Status: Phase 1B (Local Ingestion Vertical Slice) Complete

Phase 0, Phase 1A, and Phase 1B are complete. Phase 1B delivers a complete, locally runnable ingestion vertical slice covering document loading (Markdown, plain text, HTML), deterministic chunking, processed document artifact storage, atomic run manifests, and the `evidenceops-ingest` CLI entry point. No retrieval engine, vector database, embedding weights, LLM generation, API routes, or dashboard components have been initialized.

The preflight evidence is recorded in [docs/implementation-readiness.md](docs/implementation-readiness.md) and the Phase 1B milestone is documented in [docs/status/phase-1b-handoff.md](docs/status/phase-1b-handoff.md).

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
- [x] **Phase 1B: Ingestion and chunking** (Completed in full)
  - **Formats supported**: `.md`, `.markdown`, `.txt`, `.html`, `.htm`.
  - **Single-file local loader** (`src/evidenceops/ingestion/loaders.py`) with path traversal prevention, UTF-8 normalization, and size validation.
  - **HTML normalizer** (`src/evidenceops/ingestion/normalizer.py`) converting headings, lists, paragraphs, and pre/code into clean Markdown.
  - **Structure-aware Markdown chunker** (`src/evidenceops/ingestion/chunker.py`) with heading paths and atomic code-fence preservation.
  - **Paragraph-aware plain-text chunker** (`src/evidenceops/ingestion/text_chunker.py`) with configurable target/max/overlap words.
  - **Processed document artifacts** (`src/evidenceops/ingestion/artifacts.py`) stored atomically under `data/processed/<doc_id>.json`.
  - **Ingestion run manifests** (`src/evidenceops/ingestion/manifest.py`) stored atomically under `data/manifests/<run_id>.json`.
  - **Sequential local pipeline** (`src/evidenceops/ingestion/pipeline.py`) orchestrating loaders, chunkers, artifacts, and manifests.
  - **CLI command** (`src/evidenceops/cli/ingest.py` / `evidenceops-ingest`) with `--source-root`, `--run-id`, `--recursive`, `--overwrite-artifacts`.
  - **Idempotency**: Byte-identical existing artifacts are detected and reported as unchanged without rewrite or chunk duplication.
  - **Test totals**: 80 passed, 1 skipped (Windows symlink privilege check handled gracefully).
  - **Quality gates**: Ruff linting clean, Ruff formatting clean (33 files formatted), mypy strict typing clean (18 source files).
- [ ] **Phase 1C: BM25 and dense indexes** (Pending next action)
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

- Pause implementation safely per milestone instructions. On resume, begin Phase 1C by designing contract interfaces and tests for the in-process `rank-bm25` index builder.

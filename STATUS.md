# Project Status

## Current Status: Phase 1C (Local Retrieval) Implemented; Live Verification Pending

Phase 0, Phase 1A, and Phase 1B are complete. Phase 1B delivers a complete, locally runnable ingestion vertical slice covering document loading (Markdown, plain text, HTML), deterministic chunking, processed document artifact storage, atomic run manifests, and the `evidenceops-ingest` CLI entry point. No retrieval engine, vector database, embedding weights, LLM generation, API routes, or dashboard components have been initialized.

The preflight evidence is recorded in [docs/implementation-readiness.md](docs/implementation-readiness.md) and the Phase 1B milestone is documented in [docs/status/phase-1b-handoff.md](docs/status/phase-1b-handoff.md).

## Phase Roadmap & Status

- [X] **Phase 0: Environment and repository preflight** (Completed)
  - Preflight checks for tools, Git, virtual environment, and directory layout.
  - Root `EvidenceOps_SSOT.md` verified as canonical single source of truth.
  - Initial configuration templates, `.gitignore`, and documentation created.
- [X] **Phase 1A: Domain contracts and configuration** (Completed)
  - Domain enums and Pydantic v2 data models (`DocumentRecord`, `ChunkRecord`, `RetrievalAction`, `QueryIntent`, `EvidenceRecord`, `AnswerRecord`, `RunTrace`).
  - Configuration loader (`src/evidenceops/settings.py` via `pydantic-settings`).
  - Structured error types and basic structured logging interface (`src/evidenceops/logging.py`).
  - Focused unit tests for domain/state, settings, errors, and logging.
  - Verified on 2026-09-04: 17 pytest tests passed; `ruff check src tests`, `ruff format --check src tests`, and `mypy src/evidenceops` passed.
- [X] **Phase 1B: Ingestion and chunking** (Completed in full)
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
- [ ] **Phase 1C: Local retrieval subsystem** (Implementation & automated 30-question inspection complete; manual human-judgment gate pending)
  - **1C.1 (Sparse BM25)**: In-process `rank-bm25` builder, deterministic tokenizer (code & symbol preserving), atomic transparent JSON snapshots (`data/bm25/<id>.json`), deterministic tie-breaking.
  - **1C.2 (Dense & Qdrant)**: Lazy FastEmbed adapter (`BAAI/bge-small-en-v1.5`, verified 384 dimensions, 4 CPU threads), local Qdrant collection lifecycle (Cosine distance & dimension assertion), deterministic UUIDv5 point ID mapping, `DenseIndexer` batch upserting, controlled filtering. Live Qdrant integration verified.
  - **1C.3 (Hybrid RRF)**: Reciprocal Rank Fusion ($k=60$) over 1-based ranks, deterministic tie-breaking (-score, best component rank, chunk_id), `HybridRetriever` service preserving provenance.
  - **1C.4 (FlashRank Reranking)**: Bounded lazy FlashRank wrapper (`ms-marco-TinyBERT-L-2-v2`), top 20 candidate cap, top 6 retained results, uncalibrated score attribution. Real model smoke test verified.
  - **1C.5 (CLI & Integration)**: `evidenceops-index` and `evidenceops-search` command-line entry points. End-to-end integration test passes.
  - **Corpus State**: Corpus scope provisionally approved after acquisition; provenance and reproducibility corrections required before final acceptance. 10 primary-source documents pinned to exact commit SHAs and verified SHA-256 hashes (`eval/datasets/corpus_sources.json`).
  - **Retrieval Inspection**: 30-question dataset evaluated across sparse, dense, hybrid, and reranked modes (`eval/datasets/retrieval_inspection_30.json`). Diagnostic metrics and provenance stability (100.0%) computed.
  - **Pending Exit Gate**: Phase 1C implementation and automated retrieval inspection are complete, but the manual human-judgment gate remains pending review of `retrieval_inspection_review.md`.
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

- Run the explicitly marked Qdrant/FastEmbed/FlashRank smoke tests against approved local resources, then manually inspect 30 approved corpus questions before Phase 2.

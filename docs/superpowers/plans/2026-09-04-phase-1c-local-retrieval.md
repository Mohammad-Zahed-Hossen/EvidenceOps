# Phase 1C Local Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local, reproducible sparse, dense, hybrid, and reranked retrieval layer from persisted Phase 1B artifacts.

**Architecture:** Retrieval contracts return immutable, complete chunk-backed results. BM25 is rebuilt from transparent JSON; FastEmbed and Qdrant are hidden behind owned adapters, while hybrid fusion and reranking consume only the shared contracts.

**Tech Stack:** Python 3.12, Pydantic, rank-bm25, FastEmbed, qdrant-client, FlashRank, pytest, local Docker Qdrant.

**Spec:** `EvidenceOps_SSOT.md` sections 2.2-2.4, 4.4, 7, and 13; user-authorized Phase 1C implementation brief.

## Global Constraints

- Index only validated `ProcessedDocumentArtifact` JSON; never source files.
- Use deterministic ordering/ties; no pickles, cloud services, or implicit backend fallback.
- CPU-safe defaults: four embedding threads, small batches, lazy local model initialization.
- Bind Qdrant to `127.0.0.1`; default tests never require Docker or model downloads.
- Do not commit generated data, `.env`, model caches, Docker volumes, or test outputs.

### Task 1: Shared retrieval contracts and deterministic tokenizer (Phase 1C.1)

**Files:** Create `src/evidenceops/retrieval/__init__.py`, `contracts.py`, `tokenizer.py`; tests `tests/unit/test_retrieval_tokenizer.py`.

**Interfaces:** `RetrievalResult`, `SparseRetriever`, `DenseRetriever`, `Reranker`, and `DeterministicTokenizer.tokenize(text) -> tuple[str, ...]`.

- [ ] Write failing tokenizer and contract tests for identifier preservation, stopword removal, blank input, and immutable complete result records.
- [ ] Run `uv run pytest tests/unit/test_retrieval_tokenizer.py -v`; verify imports/behavior are absent.
- [ ] Implement only deterministic normalization and validated result contracts.
- [ ] Re-run focused tests, Ruff, mypy, and inspect the diff.

### Task 2: Rebuildable BM25 index (Phase 1C.1)

**Files:** Create `bm25.py`, `sparse_store.py`; tests `test_bm25_index.py`, `test_sparse_store.py`, and `tests/integration/test_sparse_artifact_retrieval.py`.

**Interfaces:** `Bm25IndexBuilder.build(processed_root)`, `Bm25Index.search(query, limit)`, `JsonSparseIndexStore.write/load`.

- [ ] Write failing tests for canonical artifact discovery, duplicate IDs, ranking/ties, full chunk resolution, transparent deterministic JSON, atomic idempotent writes, and corrupt/incompatible data.
- [ ] Confirm each test fails because the feature is missing.
- [ ] Implement validated artifact discovery, rank-bm25 runtime reconstruction, SHA-256 corpus/config fingerprints, and atomic JSON persistence.
- [ ] Run focused unit/integration tests, Ruff, mypy, and diff review.

### Task 3: Embedding and local Qdrant adapters (Phase 1C.2)

**Files:** Create `embeddings.py`, `qdrant_store.py`, `dense.py`, `docker-compose.yml`; modify `settings.py`, `.env.example`, `.gitignore`, `pyproject.toml`; tests `test_embeddings.py`, `test_qdrant_store.py`, `test_dense_retrieval.py`, `test_qdrant_dense_retrieval.py`.

**Interfaces:** `EmbeddingProvider`, lazy `FastEmbedEmbeddingProvider`, `QdrantChunkStore`, `DenseIndexer`, `DenseRetriever`.

- [ ] Write fake-backed unit tests for lazy initialization, document/query separation, finite vectors, UUIDv5 point IDs, payload allowlisting, collection compatibility, controlled filters, and unavailable Qdrant.
- [ ] Confirm failure, implement owned adapters and typed structured failures, then re-run the unit tests and static checks.
- [ ] Start only Qdrant, run explicitly marked integration test against an isolated test collection, and stop the service afterward.
- [ ] Run separately marked real FastEmbed smoke test; record actual dimension or a concrete blocker.

### Task 4: Hybrid RRF and FlashRank reranking (Phase 1C.3-1C.4)

**Files:** Create `hybrid.py`, `reranker.py`; tests `test_hybrid_retrieval.py`, `test_reranker.py`, `test_hybrid_retrieval.py` integration.

**Interfaces:** `reciprocal_rank_fusion`, `HybridRetriever`, lazy `FlashRankReranker`.

- [ ] Write failing tests for exact one-based RRF values, ties, duplicates, route-empty cases, bounded candidates, reranker provenance, and malformed/duplicate FlashRank responses.
- [ ] Verify red, implement only shared-contract orchestration, then verify green and static checks.
- [ ] Run an explicitly marked real FlashRank smoke test and record its result or blocker.

### Task 5: CLI, docs, handoff, and final verification (Phase 1C.5)

**Files:** Create `cli/retrieval.py`, `docs/status/phase-1c-handoff.md`; modify `cli/__init__.py`, `README.md`, `STATUS.md`, `DECISIONS.md`, and project configuration as needed; tests `test_retrieval_cli.py`, `test_retrieval_pipeline.py`.

**Interfaces:** `evidenceops-index` and `evidenceops-search` thin adapters over public retrieval interfaces.

- [ ] Write failing CLI tests using temporary Phase 1B artifacts; verify red.
- [ ] Implement validated build/search commands without logging query or chunk bodies; verify green.
- [ ] Run harmless CLI smoke tests, full tests and coverage, Ruff, formatting, mypy, diff check, ignored-artifact audit, and controlled live checks.
- [ ] Update only verified documentation and document unavailable live/manual gates honestly.

## Persistence and Lifecycle

`data/bm25/<safe-index-id>.json` is deterministic UTF-8 JSON (schema/version, tokenizer and BM25 config, ordered chunk IDs/tokens, artifact identities, fingerprints) written with same-directory temporary file, fsync, and replace. Qdrant stores UUIDv5 points derived from chunk ID, payload retains the original ID and allowlisted source/chunk metadata. Existing incompatible collections fail; stale points are retained until an explicit future synchronization operation.

## SSOT Ambiguities

The SSOT specifies BM25 behavior and Qdrant payload/collection constraints but not a sparse persistence schema, point-ID mapping, stale-point policy, or exact tokenizer stopword set. This plan supplies deterministic, documented implementations without changing SSOT interfaces.

## Acceptance Criteria

The Phase 1C brief's 27 completion gates are covered by Tasks 1-5. Live model/Qdrant verification and the 30-question inspection are separately documented as complete only when actually run on approved inputs.

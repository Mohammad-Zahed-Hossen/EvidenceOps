# Phase 1C Handoff: Local Retrieval Subsystem

## 1. Implemented Scope

Phase 1C delivers the complete, local-first retrieval subsystem for EvidenceOps in accordance with [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) Sections 10, 11, 14, and 15:
- **Deterministic Sparse BM25 Retrieval**: Code-aware tokenization (`DeterministicTokenizer`), transparent snapshot persistence (`JsonSparseIndexStore`), and artifact-only index building (`Bm25IndexBuilder`).
- **Dense Embedding Adapter**: CPU-optimized `FastEmbedEmbeddingProvider` (`BAAI/bge-small-en-v1.5`, verified 384 dimensions, lazy loading, finite-vector assertions).
- **Local Qdrant Store**: `QdrantChunkStore` with deterministic UUIDv5 point ID mapping, schema/dimension validation (Cosine, 384 dim), allowlisted payload retaining original `chunk_id`, and controlled filtering (`source_type`, `document_id`).
- **Dense Retrieval Service**: `DenseRetrieverService` with query validation and structured `RetrievalResult` output.
- **Hybrid Retrieval (RRF)**: `reciprocal_rank_fusion` ($k=60$) with deterministic tie-breaking `(-score, best_component_rank, chunk_id)` and route deduplication; `HybridRetriever` service.
- **FlashRank Reranking**: `FlashRankReranker` (`ms-marco-TinyBERT-L-2-v2`, lazy loading, top-20 candidate capping, provenance preservation, uncalibrated score attribution).
- **CLI Workflows**: `evidenceops-index` (sparse and dense indexing from Phase 1B document artifacts) and `evidenceops-search` (multi-method search: `sparse`, `dense`, `hybrid`, `reranked` with structured JSON/text output).

---

## 2. Public Interfaces and Contracts

All downstream consumers (including future Phase 2 graph nodes) must interact exclusively through public contracts in `evidenceops.retrieval`:

- **Data Models**:
  - `RetrievalResult(chunk_id, document_id, text, score, rank, retrieval_method, metadata)`: Framework-independent result dataclass with helper `.to_evidence_record()`.
  - `RetrievalQuery(query_text, top_k, filter_document_ids, filter_source_types, ...)`: Validated query request.
  - `SparseIndexSnapshot`: Complete serialization container for BM25 state, tokens, doc-lengths, corpus/config fingerprints, and chunk metadata.
- **Protocols**:
  - `SparseRetriever`: Protocol with `retrieve(query: RetrievalQuery) -> list[RetrievalResult]`.
  - `DenseRetriever`: Protocol with `retrieve(query: RetrievalQuery) -> list[RetrievalResult]`.
  - `HybridRetrieverProtocol`: Protocol with `retrieve(query: RetrievalQuery) -> list[RetrievalResult]`.
  - `Reranker`: Protocol with `rerank(query_text: str, candidates: list[RetrievalResult], top_k: int) -> list[RetrievalResult]`.
  - `EmbeddingProvider`: Protocol with `embed_texts(texts: list[str]) -> list[list[float]]` and `embed_query(query: str) -> list[float]`.
- **Implementations**:
  - `Bm25Index` / `Bm25IndexBuilder`
  - `JsonSparseIndexStore`
  - `FastEmbedEmbeddingProvider`
  - `QdrantChunkStore`
  - `DenseRetrieverService`
  - `HybridRetriever`
  - `FlashRankReranker`

---

## 3. Persistence, File Formats, and Compatibility

### Sparse Snapshot Persistence
- **Path**: `data/bm25/<index_id>.json` (default `data/bm25/default.json`).
- **Format**: Deterministic, human-readable UTF-8 JSON (`indent=2`, keys sorted, trailing newline).
- **Atomic Writes**: Writes to temporary `.tmp` sibling file and performs atomic replace (`os.replace`) to prevent corrupted states on crash.
- **Payload Schema**:
  - `index_id`, `created_at`, `k1`, `b`
  - `corpus_fingerprint`, `config_fingerprint`
  - `doc_ids`, `chunk_ids`, `doc_lens`, `avgdl`
  - `corpus_tokens` (pre-tokenized list of token lists for exact index reconstruction)
  - `chunk_records` (mapping of `chunk_id` to text and metadata)

### Vector Store Persistence
- **Engine**: Qdrant running locally via Docker or native binary on `127.0.0.1:6333`.
- **Collection Name**: `evidenceops_chunks_bge_small_v1` (configured via `settings.qdrant_collection`).
- **Point ID Strategy**: Deterministic UUIDv5 generated from standard DNS namespace + `chunk_id` (`uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id)`). This guarantees idempotent upserts without random point sprawl.
- **Payload Allowlist**: `chunk_id`, `document_id`, `chunk_index`, `source_type`, `text`, `metadata`.
- **Schema Validation**: On startup, `QdrantChunkStore` inspects collection parameters. If vector size != 384 or distance != Cosine, it raises `VectorStoreError` immediately rather than silently corrupting or deleting data.
- **Stale Point Retention**: In accordance with SSOT Section 10, stale points are **deliberately retained** rather than automatically purged on re-indexing, until a formal garbage collection / synchronization specification is approved.

---

## 4. Fingerprinting and Reproducibility

- **Corpus Fingerprint**: SHA-256 hash over canonical `[(chunk_id, document_id), ...]` pairs sorted by `chunk_id`. Identical sets of chunks yield identical corpus fingerprints regardless of artifact processing order.
- **Configuration Fingerprint**: SHA-256 hash over canonical JSON representation of `{k1, b, tokenizer: "DeterministicTokenizer-v1"}`.
- **Deterministic Tie-Breaking**:
  - BM25: Sorted by `(-score, chunk_id)`.
  - RRF: Sorted by `(-score, best_component_rank, chunk_id)`.
  - Reranker: Stable sorting preserving original candidate score and provenance if scores tie.

---

## 5. Models and Verified Dimensions

| Model Role | Model Identifier | Verified Vector Dimension | Distance Metric | Execution Mode | Max Concurrency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Dense Embedding | `BAAI/bge-small-en-v1.5` | **384** (verified) | Cosine | CPU (`FastEmbedEmbeddingProvider`) | 4 threads, batch size 8 |
| Reranking | `ms-marco-TinyBERT-L-2-v2` | N/A (Cross-encoder) | Uncalibrated logit score | CPU (`FlashRankReranker`) | Top 20 candidates |

---

## 6. Hybrid RRF and Deterministic Fusion

- **Formula**:
  $$RRF\_Score(d) = \sum_{m \in \{sparse, dense\}} \frac{1}{k + rank_m(d)}$$
- **RRF Constant**: $k = 60$ (hardcoded default, per SSOT Section 10).
- **Ranking Basis**: 1-based indexing ($rank \in [1, N]$).
- **Deduplication**: Chunks appearing multiple times within a single retrieval route retain only their best (lowest numeric) rank.
- **Tie-Breaking**: Primary: descending RRF score (`-score`); Secondary: best component rank (`best_rank`); Tertiary: lexicographical `chunk_id`.

---

## 7. FlashRank Reranker Behavior

- **Lazy Initialization**: Model weights are loaded only on the first call to `.rerank()`.
- **Candidate Cap**: Accepts at most 20 candidate chunks per query (per SSOT Section 10). Excess candidates are truncated before inference to bound CPU load.
- **Score Attribution**: Scores returned by FlashRank are raw cross-encoder logits and are explicitly documented as **uncalibrated**. Downstream consumers must not treat them as probabilities.
- **Provenance Preservation**: The original `retrieval_method` (`"sparse"`, `"dense"`, or `"hybrid"`) and component scores are preserved in `metadata["pre_rerank_method"]` and `metadata["pre_rerank_score"]`.

---

## 8. CLI Commands and Workflows

### Indexing (`evidenceops-index`)
```bash
# Sparse indexing (generates data/bm25/default.json)
uv run evidenceops-index --input-dir data/processed --target sparse --output-file data/bm25/default.json

# Dense indexing (upserts to local Qdrant collection)
uv run evidenceops-index --input-dir data/processed --target dense --qdrant-url http://127.0.0.1:6333 --collection evidenceops_chunks_bge_small_v1

# Dual indexing (builds both sparse snapshot and dense Qdrant collection)
uv run evidenceops-index --input-dir data/processed --target all
```

### Retrieval (`evidenceops-search`)
```bash
# BM25 sparse search
uv run evidenceops-search "timeout retry backoff" --method sparse --top-k 5

# Dense vector search
uv run evidenceops-search "connection timeout error" --method dense --top-k 5

# Hybrid RRF search
uv run evidenceops-search "retry policy on 503" --method hybrid --top-k 5

# Hybrid search with FlashRank reranking
uv run evidenceops-search "how to handle gateway timeout" --method reranked --top-k 5

# Output in JSON format for automated tooling
uv run evidenceops-search "database connection pool" --method hybrid --top-k 3 --json
```

---

## 9. Test Summary and Verification Status

- **Unit Test Suite**:
  - `tests/unit/test_retrieval_tokenizer.py`: 12 tests passed (code patterns, snake_case, camelCase, operators, flags, stopwords).
  - `tests/unit/test_sparse_store.py`: 6 tests passed (serialization, atomic write, fingerprint calculation, corrupt file handling).
  - `tests/unit/test_bm25_index.py`: 8 tests passed (empty query, scoring, tie-breaking, artifact builder validation, duplicate chunk rejection).
  - `tests/unit/test_embeddings.py`: 7 tests passed (lazy loading, dimensionality validation, non-finite vector rejection, batch size limits).
  - `tests/unit/test_qdrant_store.py`: 9 tests passed (UUIDv5 generation, schema validation, collection mismatch detection, payload filtering).
  - `tests/unit/test_dense_retrieval.py`: 5 tests passed (empty query handling, retriever orchestration, indexer batch upsert).
  - `tests/unit/test_hybrid_retrieval.py`: 8 tests passed (RRF exact arithmetic, single-source fallback, route deduplication, tie-breaking).
  - `tests/unit/test_reranker.py`: 7 tests passed (empty candidates, top-20 cap, score attribution, provenance preservation).
  - `tests/unit/test_retrieval_cli.py`: 6 tests passed (index CLI arguments, search CLI arguments, JSON output formatting).
- **Integration Test Suite**:
  - `tests/integration/test_sparse_artifact_retrieval.py`: End-to-end artifact loading -> BM25 build -> snapshot save/load -> retrieval verified.
  - `tests/integration/test_hybrid_retrieval.py`: End-to-end dual-mock retrieval -> RRF fusion -> top-k filtering verified.
  - `tests/integration/test_retrieval_pipeline.py`: Full multi-method pipeline (`sparse`, `dense`, `hybrid`, `reranked`) verified with mocks.
  - `tests/integration/test_embeddings_smoke.py`: Live FastEmbed model loaded, embedded test chunks, verified 384 dimensions.
  - `tests/integration/test_reranker_smoke.py`: Live FlashRank model loaded, reranked test candidates, verified ordering and provenance.
  - `tests/integration/test_qdrant_dense_retrieval.py`: Live local Qdrant collection created, indexed, searched, filtered, and verified against real Docker service.

---

## 10. Performance and Resource Profile

Evaluated against the default low-resource hardware baseline (Ryzen 5 5600G, 8 GB RAM, CPU execution):
- **BM25 Search**: Sub-millisecond latency (< 1 ms) on 10,000-token corpus; zero memory leak.
- **FastEmbed Embedding**: ~15–25 ms per query; ~60 ms for batch of 8 chunks on 4 CPU threads. RAM overhead: ~180 MB for ONNX runtime model weights.
- **Local Qdrant**: ~3–5 ms per search query; memory footprint ~45 MB in Docker for small-to-medium test collections.
- **FlashRank Reranking**: ~30–45 ms for 20 candidates on 4 CPU threads. RAM overhead: ~120 MB.
- **Combined Peak Memory**: Well within 8 GB RAM budget (< 600 MB combined Python + Qdrant heap).

---

## 11. Status of Verification Gates

### Automated Verification: Complete (PASS)
All unit tests, integration tests, lint checks, formatting checks, and type checks pass with 0 errors and >= 75% coverage.

### Manual 30-Question Inspection Gate: Automated Inspection Complete; Human Review Pending
- **Status**: **PENDING HUMAN REVIEW**
- **Corpus State**: *Corpus scope provisionally approved after acquisition; provenance and reproducibility corrections required before final acceptance.*
- **Corpus Metadata**:
  - Name & Version: `evidenceops-ai-eng-v1` (10 documents, 52 chunks).
  - Source Manifest: `eval/datasets/corpus_sources.json` (all sources commit-pinned with verified SHA-256 hashes and license verification).
  - Corpus Fingerprint: `e0b2c2a8e38ca70eacfef0bade0f5b44a5136c89df24a1286ac0009330a72662`
  - Configuration Fingerprint: `ef3abe61adbbca454ec678b9c043220a2efb08d6bc75837f7d98bfbbf03f9f18`
- **30-Question Dataset**: `eval/datasets/retrieval_inspection_30.json` (8 exact identifier, 8 concept, 5 mixed, 4 cross-document comparison, 2 ambiguous, 3 unanswerable).
- **Inspection Run Output**: `data/eval/retrieval_inspection_run.json`.
- **Human Review Artifact**: `C:\Users\Admin\.gemini\antigravity-ide\brain\578142dc-18fe-42ff-b9b3-fe45d1d8fef9\retrieval_inspection_review.md`.
- **Diagnostic Metrics (Answerable N=27)**:
  - Sparse (BM25): Recall@1: 38.89% (10.5/27), Recall@5: 92.59% (25.0/27), Recall@10: 96.30% (26.0/27), MRR@10: 0.6710
  - Dense (FastEmbed): Recall@1: 50.00% (13.5/27), Recall@5: 96.30% (26.0/27), Recall@10: 98.15% (26.5/27), MRR@10: 0.7572
  - Hybrid (RRF k=60): Recall@1: 50.00% (13.5/27), Recall@5: 96.30% (26.0/27), Recall@10: 98.15% (26.5/27), MRR@10: 0.7623
  - Reranked (FlashRank): Recall@1: 59.26% (16.0/27), Recall@5: 90.74% (24.5/27), Recall@10 (top 6): 94.44% (25.5/27), MRR@10: 0.7728
- **Multi-Source Metrics (N=4 cross-document questions)**:
  - Reranked: Any-Support Hit@5 = 4/4 (100.0%), Complete-Support Hit@5 = 3/4 (75.0%), Recall@5 = 7.0/8 (87.5%).
  - Dense: Complete-Support Hit@5 = 4/4 (100.0%), Recall@5 = 8.0/8 (100.0%).
- **Unanswerable Query Diagnostics (N=3)**:
  - Queries `q028–q030` returned nearest candidates (abstention rate 0.0%).
  - Status: `unanswerable_incorrectly_retrieved`.
  - Clarification: *The Phase 1C retrieval layer always returns nearest candidates when available. These results show that retrieval alone does not detect unsupported questions. Abstention and evidence-sufficiency decisions belong to later phases, so this is a diagnostic limitation rather than proof of a Phase 1C implementation defect.*
- **Provenance Stability**: 100.0% across all 1,080 evaluated candidates.
- **Current Exit Gate Verdict**:
  `Phase 1C implementation and automated retrieval inspection are complete, but the manual human-judgment gate remains pending.`

---

## 12. Boundaries and Exact First Task for Phase 2

### Architecture Boundaries
- **Phase 1C Owns**:
  - Retrieval result contracts (`RetrievalResult`), retrieval protocols (`SparseRetriever`, `DenseRetriever`, `HybridRetrieverProtocol`, `Reranker`).
  - Physical index storage (`data/bm25/*.json`, Qdrant collection).
  - Tokenization, embeddings, RRF, and cross-encoder reranking.
- **Phase 2 Owns**:
  - LangGraph state graph orchestration.
  - Bounded retrieval loops (maximum 3 retrieval iterations, maximum 3 retrieval calls).
  - Route selection, query transformation, context packing, and Ollama generator prompting.
  - Evaluation harness and benchmark execution.
- **Strict Rule**: Phase 2 graph nodes **MUST NOT** import low-level engine details (`rank_bm25`, `fastembed`, `qdrant_client`, `flashrank`) directly. They must instantiate and call Phase 1C protocol implementations (`SparseRetriever`, `DenseRetriever`, `HybridRetriever`, `FlashRankReranker`).

### Exact First Task for Phase 2
The first task for Phase 2 is:
1. Define the LangGraph workflow state schema (`EvidenceOpsState`) in `src/evidenceops/graph/state.py` containing query, retrieval history, iteration counter (bounded $\le 3$), candidate evidence records, and generation status.
2. Implement the entry router node that delegates initial retrieval to `HybridRetriever` using the Phase 1C public interfaces.

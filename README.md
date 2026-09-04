# EvidenceOps

## Retrieval Subsystem (Phase 1C)

Phase 1C provides deterministic, local-first retrieval built strictly from persisted Phase 1B processed artifacts (`data/processed/*.json`). No raw documents are re-read or re-chunked.

### 1. Start Qdrant (Docker)
```powershell
docker compose up -d qdrant
docker compose ps
```
Qdrant binds strictly to `127.0.0.1:6333`.

### 2. Build Indexes
```powershell
# Build sparse BM25 snapshot (JSON under data/bm25/)
uv run evidenceops-index --processed-root data/processed --bm25-root data/bm25 --build-sparse

# Build dense Qdrant collection using FastEmbed (bge-small-en-v1.5)
uv run evidenceops-index --processed-root data/processed --build-dense

# Build both simultaneously
uv run evidenceops-index --processed-root data/processed --bm25-root data/bm25 --build-sparse --build-dense
```

### 3. Search
```powershell
# Sparse BM25 search (does not require Docker or models)
uv run evidenceops-search --query "Qdrant payload filtering" --method sparse --top-k 5

# Dense vector search (requires Qdrant)
uv run evidenceops-search --query "vector similarity search" --method dense --top-k 5

# Hybrid search with Reciprocal Rank Fusion (RRF, k=60)
uv run evidenceops-search --query "vector indexing in python" --method hybrid --top-k 6

# FlashRank cross-encoder reranked search (TinyBERT-L-2-v2)
uv run evidenceops-search --query "vector indexing in python" --method reranked --top-k 6
```

### 4. Stop Qdrant
```powershell
docker compose stop qdrant
```

### Model Caching & Troubleshooting
- **FastEmbed**: `BAAI/bge-small-en-v1.5` downloads into OS temp / Hugging Face cache on first dense embedding invocation (~130 MB ONNX). Expected dimension is 384.
- **FlashRank**: `ms-marco-TinyBERT-L-2-v2` downloads into cache on first reranking invocation (~17 MB ONNX).
- **Qdrant Unavailable**: If Qdrant is stopped, `dense` and `hybrid` retrieval return an explicit `VectorStoreError` without silent fallback. Run `docker compose up -d qdrant`.
- **Dimension Mismatch**: If an existing Qdrant collection was created with a different embedding dimension, `VectorStoreError` is raised immediately to prevent corrupt queries.

> **Cost-Aware Retrieval and Evaluation Platform**

EvidenceOps is an AI engineering platform designed to investigate and demonstrate cost-aware, evidence-grounded information retrieval and synthesis. Rather than blindly executing fixed-top-k retrieval for every query or executing unbounded multi-agent tool loops, EvidenceOps leverages a lightweight controller to adaptively determine retrieval routing (sparse, dense, hybrid, or abstain), rerank candidate passages, verify evidence sufficiency, and synthesize verifiable answers with explicit citations while rigorously measuring latency, token consumption, and compute cost.

## Technical Authority

The authoritative technical design and specification for this project is maintained in [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md). All architectural implementations, schemas, interfaces, and evaluation protocols adhere to this Single Source of Truth.

## Local-First & Zero-Cost Policy

EvidenceOps operates under a strict **local-first and zero-cost policy**:
- **Generation**: Local Ollama instance (`qwen2.5:3b-instruct`).
- **Embedding**: In-process FastEmbed (`BAAI/bge-small-en-v1.5`) on CPU.
- **Sparse Retrieval**: In-process `rank-bm25`.
- **Vector Storage**: Local Qdrant instance.
- **Reranking**: Local FlashRank ONNX model (`ms-marco-TinyBERT-L-2-v2`).
- **Observability**: Local OpenTelemetry SDK exporting to local Jaeger.
- **No Paid APIs**: No dependency on OpenAI, Anthropic, Cohere, Pinecone, or hosted services.

## Current Implementation Status

> [!WARNING]
> **Foundation Phase**: Application features, ingestion pipelines, and model weights are **not yet implemented**. The repository is currently initialized at the clean environment and dependency baseline.

See [STATUS.md](file:///d:/Code/Assignment/EvidenceOps/STATUS.md) for current progress and [DECISIONS.md](file:///d:/Code/Assignment/EvidenceOps/DECISIONS.md) for architectural decision records.

## Quickstart & Setup

### 1. Environment Setup (uv)

```powershell
# Create virtual environment (Python 3.12)
uv venv --python 3.12 .venv

# Activate environment (PowerShell)
.venv\Scripts\Activate.ps1

# Install / sync development dependencies
uv sync --group dev
```

### 2. Configuration

```powershell
# Copy template environment configuration
Copy-Item .env.example .env
```

### 3. Local Corpus Ingestion (Phase 1B)

EvidenceOps includes a deterministic local ingestion pipeline supporting `.md`, `.markdown`, `.txt`, `.html`, and `.htm` documents:

```powershell
# Ingest local corpus
uv run evidenceops-ingest `
  --source-root data/raw `
  --run-id local-ingest-v1 `
  --recursive
```

**Output Locations**:
- Processed Document Artifacts: `data/processed/<document_id>.json`
- Ingestion Run Manifests: `data/manifests/<run_id>.json`

Refer to [docs/setup/local-development.md](file:///d:/Code/Assignment/EvidenceOps/docs/setup/local-development.md) for full setup instructions and [docs/status/phase-1b-handoff.md](file:///d:/Code/Assignment/EvidenceOps/docs/status/phase-1b-handoff.md) for the Phase 1B technical summary.

# EvidenceOps

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

Refer to [docs/setup/local-development.md](file:///d:/Code/Assignment/EvidenceOps/docs/setup/local-development.md) for full setup instructions.

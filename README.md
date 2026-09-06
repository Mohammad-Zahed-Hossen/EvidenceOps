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

### 4. Model Context Protocol (MCP) Server (Phase 2)

EvidenceOps exposes its local documentation retrieval corpus to MCP-compliant AI assistants (such as Claude Desktop or IDE MCP extensions) through a strictly local STDIO transport (`evidenceops-mcp`).

#### Allowlisted Tools
1. `search_documentation`: Query the corpus using `sparse`, `dense`, or `hybrid` retrieval with reranking. Enforces bounded `top_k` (1..20).
2. `get_document_chunk`: Fetch the full text and heading hierarchy for a specific `chunk_id`.
3. `get_source_metadata`: Retrieve provenance, license, content SHA-256, and origin metadata for a `document_id`.

#### Client Configuration (e.g. Claude Desktop / Cline / Roo Code)
Add this block to your MCP client configuration (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "evidenceops": {
      "command": "uv",
      "args": ["run", "evidenceops-mcp"],
      "cwd": "D:\\Code\\Assignment\\EvidenceOps"
    }
  }
}
```

### 5. Grounded Question Answering (Phase 3)

Use native desktop Ollama and start only the Qdrant container. Do not start an
Ollama container or the whole Compose stack on the 8 GB CPU profile.

First-time model preparation (network access is needed only to acquire missing models):

```powershell
ollama pull qwen2.5:1.5b
ollama list
docker compose up -d qdrant
```

Prepare the corpus and indexes using the ingestion/index commands above. Run a
reranked search once to populate the FlashRank cache. Dense indexing prepares
FastEmbed. The query CLI uses cached models only and returns a structured failure
if a required cache or service is unavailable; it does not download models.

Daily querying:

```powershell
uv run evidenceops-query --help
uv run evidenceops-query --query "What is dependency injection?" --json
uv run evidenceops-query --query "Compare FastEmbed and FlashRank." --max-retrieval-calls 2
uv run evidenceops-query --query "Hello!" --no-require-citations
```

Defaults: native `http://localhost:11434/v1`, `qwen2.5:1.5b`, temperature `0.0`,
60-second HTTP timeout, maximum 256 output tokens (configurable from 1 to 512).
Hard ceilings are 3 retrieval calls, 3 reformulations, 2 generation attempts,
6 context chunks, and 24,000 formatted context characters. Smaller request limits
are honored. `--no-require-citations` permits only non-factual greetings to bypass
retrieval; factual requests still require evidence and citations.

For conservative CPU smoke testing, use temporary process settings without editing `.env`:

```powershell
$env:MAX_CONTEXT_CHARS = "4000"
$env:TOP_K_CONTEXT = "2"
uv run evidenceops-query --query "What is dependency injection?" --json
Remove-Item Env:MAX_CONTEXT_CHARS
Remove-Item Env:TOP_K_CONTEXT
```

JSON distinguishes `completed`, `abstained`, and `failed`, with citation IDs,
source evidence and safe route/count diagnostics. Text mode prints the cited
source title, URI and stable chunk ID. Service failures exit nonzero; ordinary
insufficient-evidence or citation abstentions exit zero and carry their reason.
No query, prompt or document body is logged by the application; explicitly requested
JSON includes selected source text as evidence, with backend metadata allowlisted.

The sufficiency score is a deterministic heuristic, not calibrated confidence.
Unknown/malformed citations trigger one repair; continued failure causes abstention.
The 1.5B model sometimes omits citations or invents labels even after repair.
A full 24,000-character context can exceed the practical CPU timeout or the model's
available token window. Character limits are ceilings, not latency guarantees.
The 4,000-character live smoke is not a quality or performance benchmark.

### 6. Release local resources

```powershell
ollama stop qwen2.5:1.5b
docker compose stop qdrant
ollama ps
docker compose ps
```

### Phase 3 verification

```powershell
uv sync --group dev
uv run pytest -ra -q
uv run pytest --cov=src/evidenceops --cov-fail-under=75
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/evidenceops
# Run separately, serially, with prepared local services and caches:
uv run pytest -m ollama -v
uv run pytest -m qdrant -v
uv run pytest -m phase3_live -v
```

Default tests deselect `ollama`, `qdrant`, `real_model`, and `phase3_live` markers.
They require neither live daemons nor downloads. The combined live test blocks
external DNS/connections and uses the existing corpus, Qdrant, FastEmbed,
FlashRank and native Ollama. See the handoff for observed outcomes and limitations.

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
- **Generation**: Local Ollama instance (`qwen2.5:1.5b`).
- **Embedding**: In-process FastEmbed (`BAAI/bge-small-en-v1.5`) on CPU.
- **Sparse Retrieval**: In-process `rank-bm25`.
- **Vector Storage**: Local Qdrant instance.
- **Reranking**: Local FlashRank ONNX model (`ms-marco-TinyBERT-L-2-v2`).
- **Observability (planned Phase 4)**: Local OpenTelemetry and Jaeger; not implemented or started by Phase 3.
- **No Paid APIs**: No dependency on OpenAI, Anthropic, Cohere, Pinecone, or hosted services.

## Current Implementation Status

Phase 0, Phase 1A, Phase 1B, Phase 1C, and Phase 2 (MCP Foundation) are complete and verified. Phase 3 (bounded LangGraph orchestration and grounded generation) is complete and locally verified. The separate Phase 1C human judgment gate remains pending in the recorded review artifacts; no retrieval-quality improvement is claimed. See [Phase 3 handoff](docs/status/phase-3-handoff.md). See [STATUS.md](file:///d:/Code/Assignment/EvidenceOps/STATUS.md) for current progress and [DECISIONS.md](file:///d:/Code/Assignment/EvidenceOps/DECISIONS.md) for architectural decision records.

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

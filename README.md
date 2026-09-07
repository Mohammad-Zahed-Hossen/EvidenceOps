# EvidenceOps

**Cost-Aware Adaptive Retrieval & Evidence Evaluation Platform**

EvidenceOps is a locally runnable, cost-aware adaptive retrieval and evidence evaluation platform. Rather than blindly executing fixed-$k$ retrieval for every prompt or unleashing unbounded, expensive multi-agent loops, EvidenceOps dynamically routes queries to the most cost-effective retrieval strategy (sparse, dense, hybrid, or direct generation), verifies candidate evidence sufficiency and pairwise conflict, enforces mathematical iteration bounds, and synthesizes grounded answers with strict citation traceability—all operating under a **100% local-first, zero-paid-API policy**.

---

## Why EvidenceOps Exists

Standard Retrieval-Augmented Generation (RAG) implementations typically exhibit two failure modes:

1. **Fixed-Step RAG**: Blindly executes dense embedding retrieval and reranking for all queries regardless of intent. Simple queries (e.g., greetings, factual exact lookups) incur unnecessary vector search and LLM context overhead, while complex multi-step queries fail due to insufficient evidence or lack of query reformulation.
2. **Unbounded Agent Loops**: Autonomous multi-hop agents often run indefinitely, consuming unpredictable compute/memory, drifting off-topic, or generating hallucinations when evidence is absent.

EvidenceOps addresses this engineering trade-off by introducing:
- **Adaptive Retrieval Routing**: Classifies queries by intent (exact code identifiers &rarr; sparse BM25; conceptual prose &rarr; dense FastEmbed; complex synthesis &rarr; hybrid RRF; non-factual greetings &rarr; direct response).
- **Sufficiency & Conflict Guardrails**: Evaluates packed candidate evidence with deterministic heuristic scoring ($S = 0.45R + 0.25C + 0.15D + 0.15A$) and pairwise conflict detection before generation.
- **Strict Bounded Execution**: Enforces hard mathematical bounds (maximum 3 retrieval iterations, maximum 3 retrieval calls, maximum 6 chunks / 24,000 characters context) to eliminate runaway execution.
- **Auditable Citation Verification**: Requires all factual statements to reference canonical sequential citations (`[C1]`, `[C2]`), automatically attempting at most one structured repair before cleanly abstaining (`insufficient_evidence`).

---

## System Architecture

```text
                     User Query (API / CLI / Dashboard)
                                    │
                                    ▼
                         [Query Analysis Node]
                                    │
                    Extracts lexical/semantic features
                                    │
                                    ▼
                           [Controller Node]
         ┌───────────────┬──────────────────┬───────────────┐
         ▼               ▼                  ▼               ▼
      SPARSE           DENSE              HYBRID         DIRECT
    (rank-bm25)   (FastEmbed+Qdrant)   (RRF Fusion)    (Greetings)
         │               │                  │               │
         └───────────────┴────────┬─────────┘               │
                                  ▼                         │
                         [Reranker Node]                    │
                       (FlashRank ONNX)                     │
                                  │                         │
                                  ▼                         │
                     [Sufficiency & Conflict]               │
                                  │                         │
                 ┌────────────────┴───────────────┐         │
                 ▼ Sufficient                     ▼ Low     │
         [Generate Answer]               [Reformulate Query]│
         (Local Ollama LLM)                       │         │
                 │                        (Max 3 iterations)│
                 ▼                                │         │
        [Verify Citations]                        └─────────┘
        (Repair or Abstain)
                 │
                 ▼
      Final Response (Answer + Citations / Structured Abstention)
```

---

## Technology Stack

EvidenceOps relies entirely on open-source, local-first tools without paid cloud subscriptions:

| Subsystem | Technology | Execution Profile |
| :--- | :--- | :--- |
| **Generation** | Ollama (`qwen2.5:1.5b`, default) or local OpenAI-compatible endpoint | Native local process (`127.0.0.1`), temperature 0.0 |
| **Dense Embeddings** | FastEmbed (`bge-small-en-v1.5`) | In-process ONNX runtime, CPU-only (~130 MB cache) |
| **Sparse Index** | `rank-bm25` | Deterministic local JSON snapshots under `data/bm25/` |
| **Vector Database** | Qdrant | Docker container on loopback (`127.0.0.1:6333`) |
| **Cross-Encoder Reranker**| FlashRank (`TinyBERT-L-2-v2`) | Local ONNX runtime, CPU-only (~17 MB cache) |
| **Orchestration** | LangGraph | Bounded finite state machine, deterministic recursion bounds |
| **Backend API** | FastAPI / Uvicorn | Loopback-bound (`127.0.0.1:8080`), concurrency = 1 |
| **Observability & UI** | Vanilla HTML5 / CSS3 / ES6 | Same-origin, zero-CDN, zero-external-font, zero `.innerHTML` |
| **Tracing** | OpenTelemetry SDK / Jaeger | Strictly redacted spans (SHA-256 hashes, zero raw text) |
| **Tool Interface** | Model Context Protocol (FastMCP)| Local STDIO transport with 3 allowlisted tools |

### Local Generation Provider Boundary

EvidenceOps supports Ollama by default and optionally a local OpenAI-compatible chat endpoint (such as LM Studio or vLLM running on `127.0.0.1` or `localhost`). It does not support every LLM automatically and does not ship cloud-provider integrations. User-supplied endpoints in API requests, remote IP addresses, public DNS hosts, HTTPS, and API keys are strictly rejected.

---

## CPU-Safe Hardware Profile

The default configuration is specifically tuned for commodity consumer hardware:
- **Reference Target**: AMD Ryzen 5 5600G (6 cores / 12 threads), 8 GB RAM, no discrete CUDA GPU.
- **Operational Footprint**:
  - FastAPI service idle: ~62 MB RAM
  - Qdrant container: ~45 MB RAM
  - Ollama (`qwen2.5:1.5b`): ~1.2 GB RAM
  - Total measured EvidenceOps process-component footprint: **~1.35 GB RAM** (well within the 8 GB machine ceiling)
- **Concurrency**: `api_max_concurrent_queries=1` prevents thread contention and memory thrashing on CPU cores.

---

## Quickstart & Local Setup

### 1. Prerequisites
- **Python**: 3.12+
- **uv**: Modern fast Python package manager ([install guide](https://docs.astral.sh/uv/))
- **Docker Desktop / Engine**: For running Qdrant
- **Ollama**: Local model runner ([install guide](https://ollama.com/))

### 2. Installation
```powershell
# Clone the repository
git clone https://github.com/Mohammad-Zahed-Hossen/EvidenceOps.git
cd EvidenceOps

# Create environment and sync dependencies
uv sync --group dev

# Copy environment configuration template
Copy-Item .env.example .env
```

### 3. Model Preparation
```powershell
# Pull the verified CPU-safe local LLM (one-time setup)
ollama pull qwen2.5:1.5b
```

### 4. Corpus Ingestion & Indexing
```powershell
# Ingest local documentation corpus (Markdown, HTML, text)
uv run evidenceops-ingest --source-root data/raw --run-id local-ingest-v1 --recursive

# Build sparse BM25 snapshot and dense Qdrant index
docker compose up -d qdrant
uv run evidenceops-index --processed-root data/processed --bm25-root data/bm25 --build-sparse --build-dense
```

---

## Running EvidenceOps

### Option A: One-Click Desktop Launcher (Automated Lifecycle)
EvidenceOps provides automated launch scripts that start Qdrant, Ollama, and FastAPI, open the dashboard in dedicated browser app mode, and cleanly stop services and unload models upon closing:
- **Windows**: Double-click `EvidenceOps.bat` in the project root.
- **PowerShell**: Run `.\scripts\run_app.ps1`.

### Option B: Manual Service Startup
```powershell
# 1. Start Qdrant container
docker compose up -d qdrant

# 2. Launch FastAPI backend & recruiter dashboard
uv run uvicorn evidenceops.api.app:create_app --factory --host 127.0.0.1 --port 8080
```
- **Recruiter Dashboard**: Open [http://127.0.0.1:8080/](http://127.0.0.1:8080/)
- **Interactive OpenAPI Docs**: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)
- **Health Probe**: `GET /v1/health`
- **Prometheus Metrics**: `GET /v1/metrics`

### Option C: Command-Line Interface (CLI)
```powershell
# Query CLI
uv run evidenceops-query --query "What is dependency injection?" --json

# Documentation search CLI
uv run evidenceops-search --query "vector indexing" --method hybrid --top-k 5

# Local Model Context Protocol (MCP) server
uv run evidenceops-mcp
```

---

## Representative Demo Workflow

| Scenario | Input Query | Engine Behavior | Output |
| :--- | :--- | :--- | :--- |
| **1. Direct Gate** | `"Hello, what can you do?"` | Controller routes directly to generator without retrieval overhead. | Direct response explaining capabilities; 0 retrieval calls. |
| **2. Exact Identifier** | `"How is DocumentChunk id formatted?"` | Routes to sparse BM25; matches exact code symbol. | Grounded response citing `[C1]` with chunk title & URI. |
| **3. Documentation Search** | `"What is Qdrant payload filtering?"` | Routes to hybrid RRF; retrieves and reranks passages. | Synthesized technical explanation with citations `[C1]`, `[C2]`. |
| **4. Multi-Step Comparison**| `"Compare FastEmbed and FlashRank roles."` | Multi-pass adaptive retrieval; re-ranks candidates across iterations. | Bounded synthesis comparing embeddings vs rerankers; calls &le; 3. |
| **5. Unsupported Fact** | `"Who won the 2026 World Cup?"` | Sufficiency check fails ($S < 0.35$); reformulates up to 3 times. | **Structured Abstention**: Returns `"insufficient_evidence"` with zero hallucinated facts. |

---

## Evaluation & Benchmark Reproducibility

EvidenceOps includes a rigorous, frozen 100-item evaluation benchmark comparing adaptive retrieval against standard industry baselines:
- **Dataset**: `eval/datasets/evidenceops-controlled-v1.json` (60 dev / 20 validation / 20 test), partitioned with a deterministic `fact_family_id` integrity guard ensuring zero cross-split fact leakage.
- **Baselines**: `NaiveDenseRAG`, `BM25RAG`, `TwoStepHybridRAG`, and `EvidenceOpsAdaptive`.
- **Metrics**: Recall@K, MRR, nDCG, Citation Precision, Citation Recall, Lexical Fact Proxy, and Abstention Precision.
- **Statistical Significance**: Paired sign-flip permutation tests with 95% bootstrap confidence intervals ($B = 500$).

### Running Benchmarks
```powershell
# Execute reproducible evaluation runner
uv run evidenceops-eval --dataset-path eval/datasets/evidenceops-controlled-v1.json --systems adaptive,bm25,dense,hybrid
```
Benchmark outputs are saved as immutable JSON manifests and Markdown leaderboards under `eval/runs/<run_id>/`.

---

## Security, Privacy & Air-Gap Invariants

1. **Strict Localhost Boundary**: API binds exclusively to `127.0.0.1:8080`. External requests are rejected.
2. **Zero-CDN Air-Gapped Dashboard**: The web UI contains zero CDN references, zero external web fonts, and zero tracking pixels.
3. **Complete DOM Safety**: 100% of dynamic DOM updates use `textContent`, `createElement`, and `replaceChildren`. Zero `.innerHTML`, `.outerHTML`, or `insertAdjacentHTML`.
4. **Strict Telemetry Redaction**: OpenTelemetry traces export only cryptographic SHA-256 hashes and token length metrics. Raw user queries, prompts, and document text are never exported.
5. **Safe Deserialization**: Controller models use strict JSON schemas. Pickle, joblib, and arbitrary code execution are prohibited.
6. **No Runtime Downloads**: API and evaluation runtimes enforce `local_models_only=True` to prevent unauthenticated network calls to Hugging Face.

---

## Known Limitations

- **Text-Only Scope**: EvidenceOps is strictly a text and technical documentation RAG platform; it does not include OCR, image retrieval, vision-language models, or Docling integration (which is an independent external application).
- **Expert Review Status**: Gold evaluation labels are machine-generated with heuristic verification; expert human review remains marked as **pending**.
- **Sample Size & Held-out Power**: The held-out test split contains 20 items. While isolated by fact family and statistically tested with bootstrap confidence intervals, larger sample sizes are recommended for definitive production claims.
- **Learned Controller Parity**: The learned controller achieves parity with the heuristic policy (100% agreement on initial routing across the 20-item test split). The transparent heuristic controller is retained as default without exaggerated claims of superiority.
- **Local LLM Nuances**: The 1.5B parameter model (`qwen2.5:1.5b`) is tuned for CPU speed; it occasionally requires the built-in citation repair pass to conform to strict citation formatting.
- **In-Memory Run History**: The API caches the last 100 query runs in memory; history resets on server restart.

---

## Documentation Index

- [EvidenceOps Single Source of Truth (SSOT)](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md)
- [Architecture Decision Records (ADRs)](file:///d:/Code/Assignment/EvidenceOps/DECISIONS.md)
- [Project Roadmap & Status](file:///d:/Code/Assignment/EvidenceOps/STATUS.md)
- [Phase 6 Final Implementation Audit](file:///d:/Code/Assignment/EvidenceOps/docs/status/phase-6-final-audit.md)
- [Phase 4-5 Implementation Audit](file:///d:/Code/Assignment/EvidenceOps/docs/status/phase-4-5-independent-audit.md)

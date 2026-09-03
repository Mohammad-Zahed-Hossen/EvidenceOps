# EvidenceOps

## Cost-Aware Retrieval and Evaluation Platform

**Document type:** Single Source of Truth and Technical Design Document  
**Version:** 1.0  
**Status:** Implementation baseline  
**Owner:** Mohammad Zahed Hossen  
**Primary goal:** Build a credible, locally runnable AI engineering portfolio system that selects retrieval actions adaptively, produces evidence-grounded answers, and measures quality, latency, and resource cost.

---

## 0. How to use this document

This document is the implementation ground truth for EvidenceOps. Code, configuration, evaluation, and scope decisions should follow it.

If a future change affects the core objective, interfaces, data schema, evaluation protocol, or deployment model, update this document first and record the change in the decision log.

EvidenceOps is a capstone project, not the user's thesis. It is designed to demonstrate AI engineering ability through a complete, testable system. It must not be presented as a novel foundation model or as a generic chatbot.

### Explicit non-goals

- Training a large language model from scratch
- Building a general autonomous web agent
- Building a generic PDF chatbot
- Depending on OpenAI, Anthropic, Cohere, hosted vector databases, LangSmith, or other paid APIs
- Reinforcement learning for the controller in version 1
- Supporting arbitrary websites, arbitrary file formats, or unrestricted web crawling in the MVP
- Claiming research novelty merely because the system uses an agent loop

---

## 1. System overview and core philosophy

### 1.1 Problem

Conventional RAG commonly follows this pattern:

```text
Question -> dense search with fixed top-k -> fixed context -> answer
```

This creates three engineering problems:

1. Retrieval is performed even when the question is answerable without external evidence.
2. A fixed retriever and fixed top-k are weak for questions requiring reformulation, multiple sources, or different retrieval modes.
3. Agent loops can make unbounded tool calls, causing unpredictable latency, excessive context, and poor failure behavior.

EvidenceOps separates three responsibilities:

- **Control:** decide whether and how to retrieve.
- **Evidence:** retrieve, rank, filter, and assess supporting material.
- **Generation:** produce an answer constrained by accepted evidence.

The central engineering claim is:

> A lightweight retrieval controller can reduce unnecessary retrieval work and improve evidence quality compared with fixed-step RAG, while remaining locally runnable.

This is an engineering hypothesis that must be tested. It is not assumed to be true.

### 1.2 Target users and corpus

The first corpus is AI engineering documentation and code-oriented technical material:

- Python package documentation
- FastAPI, Hugging Face, LangGraph, MCP, Qdrant, and Ollama documentation
- Selected public GitHub repositories
- Carefully selected research papers and technical reports

The corpus is deliberately narrow. A focused corpus makes retrieval evaluation, citations, and failure analysis possible.

### 1.3 Product behavior

For each query, the system must:

1. Classify the query and estimate whether external evidence is required.
2. Select an initial retrieval route.
3. Retrieve from sparse, dense, or hybrid indexes.
4. Rerank candidate evidence.
5. Estimate evidence sufficiency.
6. Stop, reformulate, retrieve again, or abstain.
7. Generate an answer with source citations, or clearly report insufficient evidence.
8. Record a complete trace for debugging and evaluation.

### 1.4 Zero-cost and local-first policy

The application must run without paid API calls and without internet access during query execution, except when an explicitly enabled ingestion connector downloads a public source.

| Subsystem | Default implementation | Policy |
|---|---|---|
| Generation | Ollama local REST API | Local only |
| Embedding | FastEmbed with `BAAI/bge-small-en-v1.5` | Local CPU by default |
| Sparse retrieval | `rank-bm25` | In-process and rebuildable |
| Vector database | Qdrant in local Docker with persistent volume | No hosted Qdrant |
| Reranking | FlashRank with a small ONNX model | Local CPU |
| Orchestration | LangGraph | Local process |
| Tool protocol | MCP local server | STDIO or localhost HTTP |
| API | FastAPI | Local service |
| Dashboard | Next.js | Local development or static deployment |
| Tracing | OpenTelemetry and Jaeger | Local Docker |
| Data analysis | pandas, NumPy, matplotlib | Local notebooks/scripts |

### 1.5 Hardware reality and operating profiles

The primary machine has a Ryzen 5 5600G CPU, 8 GB RAM, and integrated graphics. The system must therefore have an explicit resource profile.

| Profile | Intended hardware | Ollama model | Concurrent queries | Use |
|---|---|---|---:|---|
| `cpu_safe` | 8 GB RAM CPU-only | A verified 1.5B to 3B instruct model | 1 | Default local profile |
| `cpu_quality` | 16 GB or more RAM | Verified 7B quantized model | 1 | Optional |
| `gpu_dev` | Colab Pro or friend's NVIDIA GPU | 7B or larger quantized model | 1 to 2 | Evaluation and demos |

The requested 7B Ollama model is not the default on the 8 GB machine. A 7B quantized model plus the operating system, Qdrant, Python, dashboard, and model runtime can cause swapping or failure. The exact model tag is configurable and must be verified with `ollama list` before use.

### 1.6 Resource budgets

These are initial engineering budgets, not guaranteed measurements.

| Metric | `cpu_safe` target | Hard guardrail |
|---|---:|---:|
| Router latency | p95 below 20 ms | 100 ms |
| Sparse retrieval | p95 below 100 ms | 500 ms |
| Dense retrieval | p95 below 500 ms | 2 s |
| FlashRank reranking | p95 below 1 s | 3 s |
| Controller decision | p95 below 100 ms | 500 ms |
| Local generation | Report actual result | 60 s request timeout |
| Retrieval iterations | 1 to 3 | Never above 3 |
| Candidate documents per iteration | 20 to 50 | Never above 100 |
| Context sent to generator | 4 to 8 chunks | Configurable hard limit |
| Simultaneous local model processes | 1 | 1 |

All performance claims in the README and CV must be measured on a named hardware profile. Never use generic claims such as "ultra-fast" without a benchmark.

### 1.7 Cost accounting

The default monetary API cost is always `$0.00` because inference and retrieval are local. EvidenceOps still records operational cost proxies:

- `retrieval_calls`
- `retrieval_candidates`
- `input_tokens_estimated`
- `output_tokens_estimated`
- `wall_time_ms`
- `peak_memory_mb` when available
- `cloud_cost_baseline_usd`, a configurable hypothetical baseline, clearly labeled as simulated

Simulated savings must never be reported as real financial savings.

---

## 2. Repository architecture

### 2.1 Directory layout

```text
evidenceops/
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
├── Makefile
├── docker-compose.yml
├── docker/
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   └── otel-collector-config.yaml
├── config/
│   ├── app.yaml
│   ├── models.yaml
│   ├── retrieval.yaml
│   └── evaluation.yaml
├── data/
│   ├── raw/                    # ignored, user-provided or downloaded sources
│   ├── processed/              # normalized documents and chunks
│   ├── manifests/              # corpus and ingestion manifests
│   ├── bm25/                   # rebuildable sparse index artifacts
│   └── eval/                   # benchmark datasets and judgments
├── src/
│   └── evidenceops/
│       ├── __init__.py
│       ├── settings.py
│       ├── logging.py
│       ├── api/
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   ├── schemas.py
│       │   └── routes/
│       │       ├── query.py
│       │       ├── evaluation.py
│       │       └── metrics.py
│       ├── domain/
│       │   ├── enums.py
│       │   ├── models.py
│       │   ├── state.py
│       │   └── errors.py
│       ├── ingestion/
│       │   ├── loaders.py
│       │   ├── normalizer.py
│       │   ├── chunker.py
│       │   ├── manifest.py
│       │   └── pipeline.py
│       ├── retrieval/
│       │   ├── bm25.py
│       │   ├── dense.py
│       │   ├── hybrid.py
│       │   ├── reranker.py
│       │   ├── filters.py
│       │   └── citations.py
│       ├── controller/
│       │   ├── features.py
│       │   ├── router.py
│       │   ├── heuristic.py
│       │   ├── model.py
│       │   ├── policy.py
│       │   └── training.py
│       ├── graph/
│       │   ├── builder.py
│       │   ├── nodes.py
│       │   └── transitions.py
│       ├── generation/
│       │   ├── ollama_client.py
│       │   ├── prompts.py
│       │   ├── grounding.py
│       │   └── abstention.py
│       ├── mcp_server/
│       │   ├── server.py
│       │   ├── tools.py
│       │   └── resources.py
│       ├── observability/
│       │   ├── tracing.py
│       │   ├── metrics.py
│       │   └── events.py
│       └── storage/
│           ├── qdrant_store.py
│           ├── artifact_store.py
│           └── run_store.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── eval/
│   ├── datasets/
│   ├── judgments/
│   ├── baselines/
│   ├── run_eval.py
│   ├── score_retrieval.py
│   ├── score_answers.py
│   ├── report.py
│   └── notebooks/
├── dashboard/
│   ├── package.json
│   ├── next.config.ts
│   └── src/
│       ├── app/
│       ├── components/
│       └── lib/
└── scripts/
    ├── ingest_corpus.py
    ├── build_bm25.py
    ├── healthcheck.py
    └── benchmark.py
```

### 2.2 Module responsibilities

- `domain`: framework-independent types and business rules.
- `ingestion`: converts source files into normalized documents, chunks, metadata, and stable IDs.
- `retrieval`: implements sparse, dense, hybrid, reranking, and citation selection.
- `controller`: chooses actions. It must not generate final answers.
- `graph`: connects the controller, retrieval, evidence checks, generation, and guardrails.
- `generation`: calls only the local Ollama endpoint and enforces evidence-grounded prompts.
- `mcp_server`: exposes narrowly scoped local tools to an MCP-compatible client or agent.
- `observability`: traces every meaningful operation and records metrics.
- `eval`: compares systems using fixed datasets and reproducible configurations.
- `dashboard`: displays query results, traces, evidence, and evaluation results.

### 2.3 Dependency rules

1. `domain` imports no application layer.
2. `controller` may depend on domain and retrieval interfaces, but not on FastAPI.
3. `api` calls application services and never accesses Qdrant directly.
4. `eval` calls public interfaces and must not modify production state.
5. All external dependencies must be wrapped behind a local interface.
6. Every model, threshold, and index parameter must come from configuration.

### 2.4 `pyproject.toml` baseline

```toml
[project]
name = "evidenceops"
version = "0.1.0"
requires-python = ">=3.11,<3.13"
dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn[standard]>=0.30,<1",
  "pydantic>=2.8,<3",
  "pydantic-settings>=2.4,<3",
  "httpx>=0.27,<1",
  "langgraph>=0.2,<1",
  "qdrant-client>=1.10,<2",
  "fastembed>=0.3,<1",
  "rank-bm25>=0.2,<1",
  "flashrank>=0.2,<1",
  "scikit-learn>=1.5,<2",
  "numpy>=1.26,<3",
  "pandas>=2.2,<3",
  "matplotlib>=3.9,<4",
  "opentelemetry-api>=1.27,<2",
  "opentelemetry-sdk>=1.27,<2",
  "opentelemetry-exporter-otlp>=1.27,<2",
  "mcp>=1.0,<2",
  "orjson>=3.10,<4",
  "tenacity>=9,<10",
]

[dependency-groups]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.24,<1",
  "pytest-cov>=5,<6",
  "ruff>=0.6,<1",
  "mypy>=1.11,<2",
  "pre-commit>=3.8,<4",
]
```

Version ranges are starting points. After the first successful installation, lock exact versions with `uv lock` and commit `uv.lock`.

---

## 3. Local infrastructure

### 3.1 Docker Compose

The dashboard is intentionally not started by default because the primary machine has only 8 GB RAM. Start it with the `dashboard` profile when needed.

```yaml
name: evidenceops

services:
  qdrant:
    image: qdrant/qdrant:v1.12.5
    restart: unless-stopped
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 10

  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    environment:
      OLLAMA_KEEP_ALIVE: "5m"
      OLLAMA_NUM_PARALLEL: "1"

  jaeger:
    image: jaegertracing/all-in-one:1.62
    restart: unless-stopped
    ports:
      - "127.0.0.1:16686:16686"
      - "127.0.0.1:4317:4317"
      - "127.0.0.1:4318:4318"
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    env_file:
      - .env
    environment:
      QDRANT_URL: http://qdrant:6333
      OLLAMA_BASE_URL: http://ollama:11434/v1
      OTEL_EXPORTER_OTLP_ENDPOINT: http://jaeger:4318
    volumes:
      - ./data:/app/data
      - ./config:/app/config:ro
    depends_on:
      qdrant:
        condition: service_healthy
      ollama:
        condition: service_started
      jaeger:
        condition: service_started

  dashboard:
    profiles: ["dashboard"]
    build:
      context: ./dashboard
      dockerfile: ../docker/dashboard.Dockerfile
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
    depends_on:
      - api

volumes:
  qdrant_storage:
  ollama_models:
```

For Windows, Docker Desktop itself may consume substantial memory. If the machine becomes unstable, run Qdrant and Jaeger in Docker but run FastAPI and the dashboard directly with `uv` and `npm`.

### 3.2 Environment variables

```dotenv
APP_ENV=local
LOG_LEVEL=INFO
API_HOST=127.0.0.1
API_PORT=8000

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=evidenceops_chunks
QDRANT_TIMEOUT_SECONDS=10

OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:3b-instruct
OLLAMA_TIMEOUT_SECONDS=60
OLLAMA_TEMPERATURE=0.0

EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
EMBEDDING_DISTANCE=Cosine

FLASHRANK_MODEL=ms-marco-TinyBERT-L-2-v2
RRF_K=60
TOP_K_SPARSE=20
TOP_K_DENSE=20
TOP_K_HYBRID=20
TOP_K_CONTEXT=6

MAX_ITERATIONS=3
MAX_RETRIEVAL_CALLS=3
MAX_CONTEXT_CHARS=24000
SUFFICIENCY_THRESHOLD=0.72
ABSTAIN_THRESHOLD=0.35

OTEL_SERVICE_NAME=evidenceops-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
SIMULATED_CLOUD_INPUT_COST_USD_PER_1K=0.0000
SIMULATED_CLOUD_OUTPUT_COST_USD_PER_1K=0.0000
```

Never commit `.env`. Commit `.env.example` only.

---

## 4. Data and ingestion design

### 4.1 Stable document model

Every ingested source becomes a `DocumentRecord`:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]+$")
    source_uri: str
    title: str
    source_type: str  # markdown, html, pdf_text, github_file, paper
    content_sha256: str
    text: str
    license_name: str | None = None
    source_updated_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    text: str
    title: str
    ordinal: int = Field(ge=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    token_estimate: int = Field(ge=1)
    metadata: dict[str, str] = Field(default_factory=dict)
```

### 4.2 Chunking policy

The initial chunker is structure-aware Markdown and HTML chunking:

- preserve headings in every chunk
- target 350 to 600 words
- overlap 50 to 80 words
- never split inside a fenced code block
- preserve source URI and heading path
- preserve code language metadata
- assign deterministic `chunk_id = sha256(document_id + ordinal + text)`

For research papers, use section-aware chunks. Do not begin with arbitrary fixed character chunks because they make citations and retrieval errors harder to diagnose.

### 4.3 Ingestion manifest

Each ingestion run writes `data/manifests/{run_id}.json` containing:

- run ID and timestamp
- source URI and checksum
- parser version
- chunker configuration
- number of documents and chunks
- embedding model name and dimension
- Qdrant collection name
- failures and warnings

Ingestion must be idempotent. Re-running an unchanged source must not create duplicate chunks.

### 4.4 Qdrant collection

For `BAAI/bge-small-en-v1.5`:

- vector dimension: `384`
- distance: cosine
- one point per chunk
- payload: `chunk_id`, `document_id`, `title`, `source_uri`, `heading_path`, `text`, `ordinal`, and metadata

The collection name is versioned when the embedding model or chunking policy changes, for example `evidenceops_chunks_bge_small_v1`.

Do not silently mix vectors generated by different models in one collection.

---

## 5. Domain state and state machine

### 5.1 Enumerations

```python
from enum import StrEnum


class QueryRoute(StrEnum):
    DIRECT = "direct"
    SPARSE = "sparse"
    DENSE = "dense"
    HYBRID = "hybrid"


class Action(StrEnum):
    STOP = "stop"
    DIRECT_ANSWER = "direct_answer"
    RETRIEVE_SPARSE = "retrieve_sparse"
    RETRIEVE_DENSE = "retrieve_dense"
    RETRIEVE_HYBRID = "retrieve_hybrid"
    REFORMULATE = "reformulate"
    RERANK = "rerank"
    ABSTAIN = "abstain"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    ABSTAINED = "abstained"
    FAILED = "failed"


class EvidenceStatus(StrEnum):
    UNKNOWN = "unknown"
    INSUFFICIENT = "insufficient"
    SUFFICIENT = "sufficient"
    CONFLICTING = "conflicting"
```

### 5.2 Complete `EvidenceOpsState`

```python
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class QueryFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_count: int = 0
    question_count: int = 0
    has_code_terms: bool = False
    has_comparison_terms: bool = False
    has_temporal_terms: bool = False
    has_multi_hop_terms: bool = False
    named_entity_count: int = 0
    estimated_subquestions: int = 1
    predicted_external_knowledge_probability: float = Field(0.0, ge=0.0, le=1.0)


class RetrievedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    title: str
    source_uri: str
    text: str
    retrieval_method: str
    retrieval_rank: int = Field(ge=1)
    retrieval_score: float = 0.0
    rerank_score: float | None = None
    citation_id: str
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievalAttempt(BaseModel):
    action: Action
    query: str
    route: QueryRoute | None = None
    candidates_returned: int = 0
    accepted_evidence: int = 0
    latency_ms: float = 0.0
    cache_hit: bool = False
    error: str | None = None


class EvidenceOpsState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus = RunStatus.CREATED
    original_query: str
    active_query: str
    query_features: QueryFeatures = Field(default_factory=QueryFeatures)
    route: QueryRoute | None = None
    next_action: Action | None = None
    iteration_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=3, ge=1, le=3)
    retrieval_calls: int = Field(default=0, ge=0)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    estimated_input_tokens: int = Field(default=0, ge=0)
    estimated_output_tokens: int = Field(default=0, ge=0)
    max_context_chars: int = Field(default=24000, ge=1000)
    query_cache_hit: bool = False
    evidence: list[RetrievedEvidence] = Field(default_factory=list)
    attempts: list[RetrievalAttempt] = Field(default_factory=list)
    evidence_status: EvidenceStatus = EvidenceStatus.UNKNOWN
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_score: float = Field(default=0.0, ge=0.0, le=1.0)
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    abstention_reason: str | None = None
    error: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

LangGraph may internally pass dictionaries between nodes. Convert dictionaries to `EvidenceOpsState` at every node boundary so validation remains centralized.

### 5.3 State transitions

| Current condition | Action | Next node |
|---|---|---|
| Query predicted external-knowledge probability below 0.20 and no citation requirement | `DIRECT_ANSWER` | local generation |
| Query contains exact API, package, class, or error identifier | `RETRIEVE_SPARSE` | BM25 retrieval |
| Natural-language semantic question with no exact identifier | `RETRIEVE_DENSE` | dense retrieval |
| Multi-hop, comparison, or code-plus-concept query | `RETRIEVE_HYBRID` | hybrid retrieval |
| Evidence exists but ranking is uncertain | `RERANK` | FlashRank |
| Sufficiency score at least `0.72`, conflict below `0.30` | `STOP` | grounded generation |
| Sufficiency below `0.72`, iterations remain, and reformulation differs | `REFORMULATE` | query reformulation |
| Sufficiency below `0.72`, reformulation is unavailable, and calls remain | retrieve selected route | retrieval node |
| Conflict at least `0.60` | `ABSTAIN` or retrieve an independent route once | conflict handler |
| Calls or iterations exhausted | `ABSTAIN` | abstention response |
| Retrieval service failure | fallback to another local route once | fallback retrieval |

### 5.4 Guardrails

The graph must stop when any guardrail is met:

- `iteration_count >= max_iterations`
- `retrieval_calls >= max_retrieval_calls`
- context exceeds `max_context_chars`
- the proposed reformulation is identical to the current query
- the same route and query have already been attempted
- the evidence set has not changed after a retry
- request timeout is reached
- local model is unavailable

No node may call an unbounded loop. The graph's maximum number of retrieval actions is three.

### 5.5 Human-readable flow

```text
Receive query
  -> validate request and create run
  -> extract cheap query features
  -> check cache
  -> direct-answer gate
       -> direct local generation, if external evidence is unnecessary
       -> otherwise select sparse, dense, or hybrid retrieval
  -> retrieve candidates
  -> merge and deduplicate evidence
  -> FlashRank reranking
  -> sufficiency and conflict evaluation
       -> sufficient and non-conflicting: grounded generation
       -> insufficient and guardrails remain: reformulate or retry
       -> conflicting: independent retrieval or abstain
       -> exhausted: abstain with diagnostics
  -> return answer, citations, trace summary, and metrics
```

---

## 6. Controller design

### 6.1 Controller responsibilities

The controller is not an LLM. It is a small decision component that predicts the next retrieval action from structured features.

Initial versions:

1. Rule-based baseline
2. Logistic Regression or small gradient-boosted classifier
3. Optional MiniLM classifier if the simpler model is insufficient

Do not start with an LLM planner. It would make latency, reproducibility, and cost attribution harder to interpret.

### 6.2 Feature extraction

Features must be available without a paid model call:

- query token count and character count
- question words
- exact identifier and code-term matches
- comparison and temporal terms
- named-entity count using lightweight heuristics
- estimated number of subquestions
- top sparse score
- top dense score
- score gap between first and second candidate
- duplicate ratio among candidates
- evidence coverage estimate
- current iteration and retrieval-call count
- elapsed time budget

The router should target under 5 ms for feature extraction and under 20 ms p95 for the complete local routing decision. Verify this with a benchmark script rather than assuming it.

### 6.3 Training data for the controller

Version 1 uses supervised labels generated from an oracle policy:

- `STOP` when accepted evidence contains the answer and has low conflict
- `RETRIEVE_SPARSE` when exact identifiers or terminology dominate
- `RETRIEVE_DENSE` when semantic similarity is required
- `RETRIEVE_HYBRID` for multi-hop or mixed terminology queries
- `REFORMULATE` when candidate evidence is relevant but incomplete
- `ABSTAIN` when the benchmark answer is not supported by the indexed corpus

The oracle must not inspect the hidden test answer during inference. Oracle labels are a training aid, not a test-time component.

### 6.4 Controller interface

```python
class ControllerDecision(BaseModel):
    action: Action
    route: QueryRoute | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str
    feature_snapshot: dict[str, float | int | bool] = Field(default_factory=dict)


class RetrievalController(Protocol):
    def decide(self, state: EvidenceOpsState) -> ControllerDecision:
        ...
```

The controller must return a reason code such as `exact_identifier`, `low_evidence_coverage`, `high_duplicate_ratio`, or `budget_exhausted`. This makes the dashboard useful and prevents opaque behavior.

---

## 7. Retrieval layer

### 7.1 Sparse retrieval

Use `rank-bm25` for the MVP because it is simple, transparent, and easy to benchmark. Tokenization must be deterministic:

- lowercase
- preserve dotted package names and error identifiers as special tokens
- split natural language punctuation
- retain code symbols where useful
- remove only a documented stopword list

The sparse index stores chunk IDs and retrieves full chunk records from the artifact store.

### 7.2 Dense retrieval

Use FastEmbed with `BAAI/bge-small-en-v1.5` by default.

Configuration:

```python
from fastembed import TextEmbedding

embedding_model = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    threads=4,
)
```

The embedding dimension is expected to be 384. Assert the actual dimension at startup and fail loudly if it differs.

### 7.3 Hybrid retrieval and RRF

Let `rank_sparse(d)` and `rank_dense(d)` be one-based ranks. Reciprocal Rank Fusion is:

\[
RRF(d) = \frac{1}{k + rank_{sparse}(d)} + \frac{1}{k + rank_{dense}(d)}
\]

Use `k = 60` initially. If a document is absent from one list, omit that term. Retrieve 20 candidates from each route, merge by chunk ID, and retain the top 20 fused candidates before reranking.

RRF is chosen because sparse and dense raw scores are not directly comparable. Do not average raw BM25 and cosine scores without normalization.

### 7.4 Qdrant interface

```python
class VectorStore(Protocol):
    def upsert(self, chunks: list[ChunkRecord], vectors: list[list[float]]) -> None:
        ...

    def search(
        self,
        vector: list[float],
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> list[RetrievedEvidence]:
        ...
```

Use payload filtering for `source_type`, document ID, and optional collection tags. Never expose arbitrary filter expressions directly from the public API.

### 7.5 FlashRank reranking

FlashRank reranks the top hybrid candidates. Initial configuration:

- model: `ms-marco-TinyBERT-L-2-v2`
- max rerank candidates: 20
- retain top 6 for generation
- normalize scores only for comparison within the current query

Do not interpret reranker scores as calibrated probabilities. The sufficiency score is a separate composite score.

### 7.6 Evidence sufficiency

Initial composite sufficiency score:

\[
S = 0.45R + 0.25C + 0.15D + 0.15A
\]

Where:

- `R`: normalized reranker relevance
- `C`: answer coverage, based on question entities and terms found in evidence
- `D`: diversity across documents or sections
- `A`: answerability score from a local extractive check or local judge

Initial thresholds:

- `S >= 0.72`: sufficient
- `0.35 <= S < 0.72`: uncertain, retry if budget remains
- `S < 0.35`: insufficient
- conflict score `>= 0.60`: conflicting evidence

These thresholds are calibration parameters. They must be tuned on a validation split and reported with the final benchmark.

### 7.7 Citation policy

Every generated factual claim must be supported by one or more returned chunk IDs. The final response must include:

```text
[C1] Document title, section, source URI
[C2] Document title, section, source URI
```

If evidence is insufficient, the system must say so. It must not invent a citation or silently answer from model memory.

---

## 8. Generation layer

### 8.1 Ollama client

The client uses the OpenAI-compatible local endpoint only because it provides a familiar interface. No external OpenAI service is involved.

```python
import httpx


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
        return body["choices"][0]["message"]["content"]
```

### 8.2 Grounded generation rules

The generation prompt must instruct the model to:

- answer only from supplied evidence
- cite evidence IDs inline
- distinguish direct evidence from inference
- report conflicting sources
- refuse unsupported claims
- avoid mentioning hidden chain-of-thought
- return a structured answer envelope when requested

The system must not request or display private chain-of-thought. Store tool events, decisions, scores, and short reason codes instead.

### 8.3 Abstention response

```json
{
  "status": "abstained",
  "answer": "I could not find sufficient evidence in the indexed corpus.",
  "citations": [],
  "reason": "evidence_below_threshold_after_max_iterations",
  "retrieval_summary": {
    "calls": 3,
    "iterations": 3,
    "top_sufficiency_score": 0.31
  }
}
```

---

## 9. MCP integration

MCP is an integration boundary, not the core intelligence of EvidenceOps. The system must work without an MCP client.

### 9.1 Local MCP tools

Expose only these tools in version 1:

| Tool | Purpose |
|---|---|
| `search_documentation` | Search indexed technical documents |
| `get_document_chunk` | Retrieve one exact chunk by ID |
| `get_source_metadata` | Return title, URI, license, and update metadata |
| `run_evidence_query` | Execute the full EvidenceOps workflow |
| `get_run_trace` | Read a completed run's structured trace |

### 9.2 Tool schema

```json
{
  "name": "search_documentation",
  "description": "Search the local EvidenceOps corpus and return ranked evidence chunks.",
  "inputSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "query": {"type": "string", "minLength": 2, "maxLength": 1000},
      "mode": {"type": "string", "enum": ["sparse", "dense", "hybrid"]},
      "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
      "source_type": {"type": "string"}
    },
    "required": ["query"]
  }
}
```

MCP tools must enforce the same limits as the internal API. Never allow an MCP caller to execute arbitrary shell commands, arbitrary URLs, unrestricted filesystem paths, or raw database queries.

### 9.3 MCP transport

Use STDIO for local desktop integration first. Add localhost HTTP only after the tool contracts are tested. Authentication is not required for a strictly localhost-only MVP, but the API must bind to `127.0.0.1`, not `0.0.0.0`.

---

## 10. FastAPI API layer

### 10.1 Request and response schemas

```python
from datetime import datetime
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    collection: str = "evidenceops_chunks"
    require_citations: bool = True
    max_iterations: int = Field(default=3, ge=1, le=3)
    debug: bool = False


class Citation(BaseModel):
    citation_id: str
    chunk_id: str
    title: str
    source_uri: str
    excerpt: str


class QueryResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None
    citations: list[Citation]
    route: str | None
    retrieval_calls: int
    iterations: int
    latency_ms: float
    sufficiency_score: float
    abstention_reason: str | None = None
    trace_id: str | None = None


class EvaluationRunRequest(BaseModel):
    dataset_name: str
    systems: list[str] = Field(default=["dense_rag", "two_step_hybrid", "evidenceops"])
    limit: int | None = Field(default=None, ge=1, le=10000)


class EvaluationRunResponse(BaseModel):
    evaluation_id: str
    status: str
    dataset_name: str
    output_path: str | None = None


class MetricsResponse(BaseModel):
    service: str
    uptime_seconds: float
    total_queries: int
    completed_queries: int
    abstained_queries: int
    average_latency_ms: float
    p95_latency_ms: float
    average_retrieval_calls: float
```

### 10.2 Endpoints

```text
POST /v1/query
POST /v1/eval/run
GET  /v1/eval/{evaluation_id}
GET  /v1/metrics
GET  /v1/health
GET  /v1/runs/{run_id}
```

### 10.3 API rules

- validate all input with Pydantic
- cap query length and iteration count
- use request IDs and trace IDs
- do not block the event loop with embedding, reranking, or local model calls
- use `asyncio.to_thread` or Starlette's threadpool for blocking libraries
- return `504` on local model timeout
- return `503` when Qdrant or Ollama health checks fail
- return a structured abstention response, not a generic `500`, when evidence is insufficient
- make evaluation jobs asynchronous after the MVP endpoint is stable

---

## 11. Observability

### 11.1 Trace hierarchy

Create one root span per query:

```text
evidenceops.query
├── evidenceops.query_features
├── evidenceops.cache_lookup
├── evidenceops.controller_decision
├── evidenceops.retrieval.sparse
├── evidenceops.retrieval.dense
├── evidenceops.retrieval.hybrid
├── evidenceops.rerank.flashrank
├── evidenceops.evidence.sufficiency
├── evidenceops.generation.ollama
└── evidenceops.response
```

Only spans that execute should be created. A skipped dense search should be recorded as a decision event, not as a fake successful retrieval span.

### 11.2 Required span attributes

- `run.id`
- `query.hash`, never raw sensitive query text by default
- `controller.action`
- `controller.confidence`
- `retrieval.route`
- `retrieval.top_k`
- `retrieval.calls`
- `retrieval.candidates`
- `retrieval.cache_hit`
- `embedding.model`
- `reranker.model`
- `generation.local_model`
- `generation.input_tokens_estimated`
- `generation.output_tokens_estimated`
- `evidence.sufficiency_score`
- `evidence.conflict_score`
- `answer.citation_count`
- `run.abstained`
- `simulated.cloud_cost_usd`

Do not export full document contents or user queries to Jaeger by default. Store detailed evidence in local run artifacts and use hashes or truncated fields in traces.

### 11.3 Metrics

Record:

- request count by status
- latency histogram by route and endpoint
- p50, p95, and p99 latency
- retrieval calls per query
- controller action distribution
- cache hit ratio
- abstention ratio
- evidence sufficiency distribution
- citation count
- Qdrant errors
- Ollama timeouts
- evaluation scores by system

---

## 12. Evaluation protocol

### 12.1 Evaluation principle

The project is not complete when the demo works. It is complete when the system is compared against baselines using a fixed dataset, fixed corpus, fixed model configuration, and reproducible metrics.

### 12.2 Benchmark datasets

Use two evaluation layers:

**Layer A, controlled development set**

Create 100 to 200 questions from the indexed documentation. Include:

- direct factual questions
- exact API and error questions
- semantic concept questions
- comparison questions
- two-hop questions
- unanswerable questions
- deliberately ambiguous questions

Each item must include gold answer facts and gold supporting chunk IDs.

**Layer B, public benchmark**

Use a suitable public multi-hop or retrieval benchmark after the local pipeline is stable. Record the exact dataset version, license, split, and preprocessing method.

Do not mix development questions with final test questions.

### 12.3 Required baselines

1. **Naive Dense RAG:** one dense search, fixed top-k, one generation call.
2. **BM25 RAG:** one sparse search, fixed top-k.
3. **Two-Step Hybrid:** always performs two hybrid retrieval actions.
4. **Heuristic EvidenceOps:** rule-based controller.
5. **Learned EvidenceOps:** trained lightweight controller.
6. **ReAct-style baseline:** only if a fully local generator and tool loop can be run reproducibly. It is optional, not a dependency.

The comparison must keep the corpus, generator, context limit, and answer prompt equivalent wherever possible.

### 12.4 Metrics

For a query with relevant set `Rel`:

\[
Recall@K = \frac{|Rel \cap Retrieved@K|}{|Rel|}
\]

\[
MRR = \frac{1}{N}\sum_{i=1}^{N}\frac{1}{rank_i}
\]

For nDCG:

\[
nDCG@K = \frac{DCG@K}{IDCG@K}
\]

Also report:

- exact match or answer F1 where applicable
- citation precision and citation recall
- supported-claim rate
- abstention precision on unanswerable questions
- average, p50, p95, and p99 latency
- average retrieval calls
- context characters and token estimates
- peak memory where measurable

### 12.5 Citation evaluation

The primary citation score is deterministic:

```text
citation_precision = cited_supporting_chunks / cited_chunks
citation_recall = cited_supporting_chunks / required_supporting_chunks
```

An optional local LLM judge may assess answer faithfulness using Ollama, but it is secondary because local judge models can be unreliable. Store the judge model, prompt, temperature, and full result. Never present LLM-as-a-judge scores as ground truth.

RAGAS may be used as an experimental comparison, but it must not be the only evaluation method because some RAGAS metrics require an LLM judge and can add runtime complexity.

### 12.6 Required ablations

- dense only versus BM25 only versus hybrid
- no reranker versus FlashRank
- fixed top-k versus adaptive top-k
- heuristic controller versus learned controller
- one iteration versus up to three iterations
- sufficiency threshold values 0.60, 0.72, and 0.85
- with and without query reformulation

### 12.7 Acceptance criteria

The MVP passes only if:

- all core unit and integration tests pass
- ingestion is repeatable without duplicate chunks
- Qdrant collection startup and health checks work
- local Ollama generation works with the selected model
- every answer has traceable citations or a clear abstention
- no query exceeds three retrieval iterations
- baseline comparison produces a machine-readable report
- dashboard displays at least one complete query trace
- measured p95 latency and memory are documented
- the learned controller is not claimed as an improvement unless test-set evidence supports it

---

## 13. Testing strategy

### 13.1 Unit tests

Test:

- chunk ID determinism
- Markdown/code-block preservation
- BM25 tokenization
- RRF ranking
- score normalization
- sufficiency threshold decisions
- controller guardrails
- state validation
- citation formatting
- cost and latency aggregation

### 13.2 Integration tests

Run against local Qdrant and a mocked Ollama client first. Then run a smaller smoke test against the real Ollama service.

Test:

- ingestion to Qdrant
- search to evidence object conversion
- LangGraph completion
- abstention after maximum iterations
- local model timeout
- API response contracts
- trace creation

### 13.3 Contract tests

Validate MCP tool schemas and FastAPI OpenAPI output. A change to a tool or API schema requires updating the corresponding contract test.

### 13.4 Quality gates

```text
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pytest --cov=src/evidenceops --cov-fail-under=75
```

The 75 percent threshold applies to core logic, not generated dashboard code or notebooks.

---

## 14. Eight-week implementation roadmap

The roadmap assumes approximately 10 to 15 focused hours per week. If time is lower, remove the learned controller or MCP integration before removing evaluation and tests.

### Week 1, foundations and corpus

Checklist:

- [ ] create repository and `uv` project
- [ ] create configuration and environment model
- [ ] implement document and chunk schemas
- [ ] select a small licensed corpus
- [ ] implement Markdown and HTML ingestion
- [ ] implement deterministic chunking and manifests
- [ ] write ingestion tests

Deliverable: a command that converts a small corpus into reproducible chunks and metadata.

Exit gate: the same input produces the same chunk IDs and no duplicate chunks.

### Week 2, local indexes and MCP foundation

Checklist:

- [ ] start Qdrant locally
- [ ] create versioned collection with dimension assertion
- [ ] generate FastEmbed vectors
- [ ] build BM25 index
- [ ] implement sparse, dense, and hybrid retrieval interfaces
- [ ] implement RRF
- [ ] create MCP search and chunk tools

Deliverable: CLI and MCP calls return ranked evidence with source metadata.

Exit gate: retrieval quality is manually inspected on at least 30 questions and all returned chunks have stable citations.

### Week 3, orchestration and generation

Checklist:

- [ ] implement Ollama client
- [ ] implement grounded prompt and citation formatter
- [ ] implement Pydantic state
- [ ] build LangGraph nodes
- [ ] implement direct-answer gate
- [ ] implement retrieval, reranking, sufficiency, generation, and abstention nodes
- [ ] enforce iteration and retrieval-call limits

Deliverable: end-to-end local query execution.

Exit gate: the system can complete, retry, and abstain without unbounded loops.

### Week 4, heuristic controller

Checklist:

- [ ] implement feature extraction
- [ ] implement deterministic router
- [ ] implement heuristic action policy
- [ ] write controller benchmarks
- [ ] add query and result caching if useful
- [ ] add structured run artifacts

Deliverable: adaptive retrieval works without an LLM planner.

Exit gate: controller p95 decision latency is measured and all decisions have reason codes.

### Week 5, learned controller

Checklist:

- [ ] create training examples from the development corpus
- [ ] generate oracle action labels
- [ ] train Logistic Regression baseline
- [ ] evaluate accuracy, macro F1, and action confusion matrix
- [ ] integrate the learned controller behind a configuration flag
- [ ] preserve heuristic fallback

Deliverable: learned controller can be selected without changing the graph interface.

Exit gate: learned controller does not reduce reliability on the validation set. If it does, retain the heuristic controller and document the result.

### Week 6, evaluation harness and observability

Checklist:

- [ ] implement baseline systems
- [ ] implement retrieval metrics
- [ ] implement answer and citation metrics
- [ ] instrument OpenTelemetry spans
- [ ] start Jaeger locally
- [ ] write JSONL run and result formats
- [ ] generate CSV and matplotlib reports

Deliverable: one command runs all systems on the same dataset and produces a comparison report.

Exit gate: every result is linked to dataset version, corpus version, model configuration, and code commit.

### Week 7, FastAPI and dashboard

Checklist:

- [ ] implement `/v1/query`
- [ ] implement health and metrics endpoints
- [ ] implement asynchronous evaluation job endpoint
- [ ] build query interface
- [ ] build evidence and citation panel
- [ ] build retrieval trajectory panel
- [ ] build latency and evaluation charts

Deliverable: a recruiter can run a query and see why the system made its decisions.

Exit gate: API contract tests pass and the dashboard does not expose raw secrets or unrestricted filesystem access.

### Week 8, hardening and portfolio packaging

Checklist:

- [ ] run clean-machine setup from README
- [ ] test CPU-safe profile
- [ ] record measured resource and latency results
- [ ] add screenshots or a short demo recording
- [ ] write architecture and evaluation documentation
- [ ] document limitations and failed experiments
- [ ] create a reproducible benchmark command
- [ ] prepare CV bullet and interview explanation

Deliverable: version `1.0.0` portfolio release.

Exit gate: another engineer can clone the repository, start the local stack, ingest the sample corpus, run a query, and reproduce the evaluation report without paid credentials.

---

## 15. Configuration and scope control

### MVP must include

- local corpus ingestion
- BM25, dense, and hybrid retrieval
- FlashRank reranking
- heuristic controller
- Pydantic state machine
- local Ollama generation
- citations and abstention
- FastAPI query endpoint
- evaluation against at least three baselines
- basic OpenTelemetry trace

### Version 1.1 may include

- learned Logistic Regression controller
- MCP STDIO server
- query/result cache
- dashboard trace visualization
- local LLM-as-a-judge comparison

### Explicitly defer

- multimodal page-image retrieval
- ColPali or late-interaction visual retrieval
- reinforcement learning
- web-scale crawling
- distributed workers
- authentication and multi-tenant deployment
- Kubernetes
- production cloud deployment

The multimodal extension can become a later branch because it connects naturally to the user's VLM field, but adding it before the text-first evaluation is complete will make the capstone harder to finish and harder to evaluate.

---

## 16. Failure modes and responses

| Failure | Detection | Response |
|---|---|---|
| Ollama unavailable | health check or timeout | return structured service-unavailable error |
| Qdrant unavailable | health check | use no silent in-memory substitute in production mode |
| low evidence quality | sufficiency score | reformulate, retry, or abstain |
| conflicting documents | conflict score | retrieve independent evidence or abstain |
| repeated query | attempt history | stop and abstain |
| high memory pressure | OS/runtime monitoring | unload model, reduce context, use `cpu_safe` profile |
| malformed source | ingestion validation | skip source, record manifest failure |
| hallucinated citation | citation validator | reject answer and regenerate once, then abstain |
| learned controller regression | fixed evaluation set | fall back to heuristic policy |
| dashboard failure | API remains healthy | CLI and API remain the source of truth |

---

## 17. Security and privacy baseline

- bind local services to `127.0.0.1`
- do not log full queries or document content by default
- do not execute arbitrary code from retrieved documents
- treat retrieved text as untrusted input
- prevent prompt injection from changing tool permissions
- expose allowlisted MCP tools only
- restrict ingestion paths to configured directories
- restrict optional URL ingestion to explicitly enabled domains
- never store API keys because the default system has none
- sanitize source filenames and metadata
- keep local data and traces outside version control

MCP must be treated as a tool boundary. A retrieved document can contain instructions, but those instructions are data and must never grant new permissions.

---

## 18. Portfolio and CV positioning

### Project description

> EvidenceOps is a zero-cost, locally runnable retrieval platform that uses a lightweight controller to select sparse, dense, hybrid, reformulation, reranking, or stop actions. It returns evidence-grounded answers with citations, bounded execution, abstention behavior, latency measurement, and end-to-end traces.

### CV bullet after measured completion

> Built a local cost-aware retrieval platform with FastAPI, Qdrant, FastEmbed, BM25, FlashRank, Ollama, LangGraph, MCP, and OpenTelemetry; implemented bounded adaptive retrieval with citation validation and benchmarked quality, latency, retrieval calls, and abstention against fixed-step RAG baselines.

Do not include improvement percentages until they have been measured on a held-out test set and the baseline configurations are documented.

### Interview demonstration sequence

1. Ask a direct documentation question and show the retrieval gate.
2. Ask a multi-hop question and show multiple retrieval actions.
3. Ask an unanswerable question and show abstention.
4. Open the trace and show latency per component.
5. Open the evaluation report and explain the baseline comparison.
6. Explain one failure case and the engineering decision made in response.

This demonstration is more valuable than a polished chat interface alone.

---

## 19. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-09-03 | Project is a capstone and hiring portfolio project, not thesis research | Keeps evaluation and engineering value central |
| 2026-09-03 | Zero paid APIs and local-first architecture | Matches budget and reproducibility constraints |
| 2026-09-03 | Text-first corpus for MVP | Makes retrieval quality and citations measurable |
| 2026-09-03 | Controller separated from generator | Enables latency, policy, and ablation analysis |
| 2026-09-03 | Maximum three retrieval iterations | Prevents unbounded agent behavior |
| 2026-09-03 | Heuristic controller before learned controller | Provides a strong transparent baseline |
| 2026-09-03 | Qwen 7B is optional, not default on 8 GB RAM | Prevents local resource failure |
| 2026-09-03 | Evaluation and observability are release requirements | Prevents a demo-only project |
| 2026-09-03 | Multimodal retrieval is deferred | Avoids combining two difficult systems before the baseline is valid |

---

## 20. Final definition of done

EvidenceOps is complete for portfolio release when all of the following are true:

- [ ] local setup works without paid credentials
- [ ] sample corpus ingestion is reproducible
- [ ] sparse, dense, and hybrid retrieval work
- [ ] the controller selects bounded actions
- [ ] retries and reformulations terminate safely
- [ ] answers include valid citations or abstain
- [ ] FastAPI exposes the documented endpoints
- [ ] MCP tools expose only the documented capabilities
- [ ] traces show the complete query path
- [ ] evaluation compares fixed baselines and EvidenceOps
- [ ] latency, retrieval calls, memory profile, and limitations are documented
- [ ] tests, lint, and clean-machine setup pass
- [ ] README contains a short demo path and measured results

The project is not considered complete merely because a local chatbot can answer questions.

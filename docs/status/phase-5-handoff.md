# Phase 5 Handoff: Local FastAPI Service and Recruiter-Facing Observability Dashboard

## 1. Overview & Architecture

Phase 5 delivers a secure, local-first FastAPI service and a unified same-origin observability dashboard for EvidenceOps. Operating under strict 8 GB RAM and single-CPU constraints, the service exposes bounded retrieval, health telemetry, metrics, and background benchmark evaluation without external cloud dependencies, hosted vector databases, or third-party frontend frameworks.

### Architecture Highlights:

- **Zero Hosted / Cloud Dependencies**: Bounded strictly to localhost (`127.0.0.1`), operating directly with local Qdrant, FastEmbed (`bge-small-en-v1.5`), FlashRank (`ms-marco-TinyBERT-L-2-v2`), and native Ollama (`qwen2.5:1.5b`).
- **Bounded Concurrency Controls**: Prevents CPU saturation and RAM exhaustion using `asyncio.Semaphore` guards (`api_max_concurrent_queries=1`, `api_max_concurrent_evaluations=1`) and non-blocking worker thread offloading (`asyncio.to_thread`).
- **Standardized Error Envelope**: All 4xx and 5xx responses conform to `{"error": {"code": "...", "message": "...", "details": ...}}`. Internal exceptions, stack traces, and local disk paths (`D:\...`) are completely redacted.
- **Same-Origin Recruiter Dashboard**: Single-page dashboard served directly at `GET /` with static assets mounted at `/static/`. Built with vanilla semantic HTML5, modern vanilla CSS, and safe vanilla JavaScript with zero external CDNs, external web fonts, or npm dependencies.
- **Asynchronous Evaluation Runner**: Threaded background benchmark execution via allowlisted `POST /v1/eval/run` and polling via `GET /v1/eval/{evaluation_id}`. Emits artifacts strictly to relative paths under `eval/runs/<run_id>/`.

---

## 2. API Endpoints Specification

| Method   | Route                        | Description                                                 | Concurrency & Validation Bounds                                                                                 |
| :------- | :--------------------------- | :---------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/v1/health`               | Probes Qdrant, Ollama, BM25, and Eval dataset readiness     | Non-blocking, cheap probes. Returns`ready`, `degraded`, or `unavailable`.                                 |
| `GET`  | `/v1/metrics`              | Prometheus-style counters, gauges, and latency stats        | In-memory atomic tracking. Never hits disk or models.                                                           |
| `POST` | `/v1/query`                | Bounded retrieval, citation validation, and grounded answer | Query length`[2..2000]`, max iterations `[1..3]`. Returns `200 OK` or `429` if busy.                    |
| `GET`  | `/v1/runs/{run_id}`        | Look up completed query trajectory and telemetry            | Bounded FIFO memory registry (max 100 runs). Returns`200` or `404`.                                         |
| `POST` | `/v1/eval/run`             | Launch asynchronous benchmark evaluation in background      | Strictly allowlisted`evidenceops-controlled-v1` and system IDs. Returns `202 Accepted` or `409 Conflict`. |
| `GET`  | `/v1/eval/{evaluation_id}` | Poll background evaluation job status and artifacts         | Non-blocking polling. Returns status (`queued`, `running`, `completed`, `failed`).                      |
| `GET`  | `/`                        | Serves dashboard UI (`index.html`)                        | Same-origin HTML with zero external CDN references.                                                             |
| `GET`  | `/static/*`                | Serves`styles.css` and `app.js`                         | Vanilla assets with strict XSS-safe DOM manipulation.                                                           |

---

## 3. Security, Privacy & Resource Governance

1. **Host Binding**: Validated strictly to loopback (`127.0.0.1`, `localhost`). Non-loopback bindings (such as `0.0.0.0`) are forbidden at startup.
2. **Path & Trace Redaction**: Local filesystem paths (`D:\Code\...`) are replaced with sanitized identifiers or relative references (`runs/<run_id>/leaderboard.md`).
3. **Trace Attributes**: OpenTelemetry spans adhere to `RedactionPolicy`, hashing query content and chunk texts to ensure zero raw data leakage.
4. **XSS Defense**: `app.js` uses `textContent` and `createElement` exclusively. No dynamic `innerHTML` interpolation is permitted.
5. **Memory Cap**: In-memory run summaries are bounded by a FIFO cache (`api_run_history_limit=100`) to guarantee zero memory leaks over extended operation.

---

## 4. Verification Evidence

### Automated Test Suite

- `tests/unit/api/test_health_metrics.py`: Probes, metrics aggregation, OpenAPI schema generation without model downloads.
- `tests/unit/api/test_query_api.py`: Input length bounds, extra field rejection, semaphore concurrency limits, structured abstention, run lookup.
- `tests/unit/api/test_eval_api.py`: Dataset allowlisting, system verification, background execution lifecycle, concurrency guard.
- `tests/unit/api/test_dashboard_contract.py`: Route verification, static asset delivery, CDN isolation check, innerHTML absence check.

```text
============================== 25 passed in 20.05s ==============================
```

### Static Analysis & Linters

- `ruff check src tests scripts`: Passed (0 errors).
- `ruff format --check src tests scripts`: Passed (0 formatting changes required).
- `mypy src/evidenceops`: Passed (0 type errors).

---

## 5. How to Run the Dashboard & API Locally

Start the local FastAPI service using Uvicorn:

```bash
uv run uvicorn evidenceops.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open a browser and navigate to:

```text
http://127.0.0.1:8000/
```

Interactive OpenAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

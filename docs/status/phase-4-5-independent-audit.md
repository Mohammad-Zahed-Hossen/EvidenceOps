# Phase 4–5 Independent Implementation Audit and Targeted Remediation

> [!NOTE]
> **Historical Pre-Phase-6 Record:** This audit records the independent baseline verification of Phases 4 and 5 prior to Phase 6. Phase 6 (hardening, recruiter trajectory UX, operational smoke suite, and portfolio release) was subsequently completed and is documented in [docs/status/phase-6-final-audit.md](phase-6-final-audit.md).

**Audit Date:** 2026-09-06
**Repository:** `D:\Code\Assignment\EvidenceOps`
**Inspected Commits:** `9b4f43f`, `7e305e4`, `443db57`, `506da09`, and `c5b47e7` on `main`
**Auditor:** Independent Fresh-Context Audit Agent
**Scope:** Phase 4 (Evaluation, Benchmarking, Metrics & Local Observability) and Phase 5 (Local FastAPI Service & Dashboard) pre-Phase-6 baseline. Phase 6 was not started at the time of this audit.

---

## 1. Executive Completion Verdict

- **Phase 4 Completion Verdict:** **Independently Verified** for its documented localhost MVP scope.
  - Dataset contracts, baseline adapters, scoring metrics, statistical resampling, and safe non-executable linear model serialization are verified.
  - Limitations on human review (marked pending) and held-out claim qualifications are explicitly preserved.
- **Phase 5 Completion Verdict:** **Independently Verified** for its documented localhost MVP scope.
  - Localhost binding (`127.0.0.1:8080`), local-request boundaries, strict input validation, concurrency serialization (1 active query, 1 active eval), clean cancellation, safe status mapping, and safe same-origin DOM dashboard rendering are verified.

> **Independent Certification:**
> **Phase 4 and Phase 5 are independently verified for their documented localhost MVP scope.**

---

## 2. Audit Matrix

| Area | SSOT Requirement | Current Implementation Evidence | Severity | Status | Action Taken |
|---|---|---|---|---|---|
| **Tracing & Telemetry** | Strict trace redaction; zero text leakage | Attribute dictionary filtered against strict allowlist (`TEXT_KEYS` hashed/counted, `COUNTER_KEYS` bounded finite, `ENUM_VALUES` checked); `record_exception=False` prevents raw exception text leak | **P0** | Resolved | Allowlist enforcement in `tracing.py`; validated by `test_audit_redaction.py` |
| **Model Deserialization** | Safe optional controller artifact; zero code execution | Replaced `joblib`/`pickle` arbitrary code execution with bounded JSON schema (schema version 1, linear coefficients, intercept, classes); strict dimension and finite bounds | **P0** | Resolved | JSON linear model format implemented in `training.py`; verified by `test_audit_model.py` |
| **API Concurrency & Cancellation** | 1 active query; cancellation must not leak worker capacity | `threading.Lock` acquired per query/eval; worker task shielded so client disconnection keeps capacity occupied until worker completes and metrics are recorded | **P0** | Resolved | Added worker shielding and cancellation retention in `query.py` and `service.py`; verified by `test_audit_api.py` |
| **Evaluation Dataset Citations** | Gold citations must reference valid processed document IDs | All 119 citations in `evidenceops-controlled-v1.json` used filenames instead of frozen document IDs; updated citations to canonical IDs and regenerated SHA256 identity | **P1** | Resolved | Repaired citation references in `evidenceops-controlled-v1.json` and updated `evidenceops-controlled-v1.identity.json`; verified by `test_audit_dataset.py` |
| **Scoring & Metrics** | Correct arithmetic; no duplicate citation or DCG credit | Duplicate retrieved chunks no longer receive repeated DCG/citation credit; fact matching labeled as lexical proxy; sign-flip randomization test for small-sample p-values | **P1** | Resolved | Fixed arithmetic in `metrics.py` and `statistics.py`; verified by `test_audit_metrics.py` |
| **Baseline Fairness** | Equal context bounds and valid chunk contracts | Baselines now receive full chunk excerpts instead of placeholders; hybrid passes valid `RetrievalResult` objects to FlashRank; equal `top_k` and `max_context_chars` shared | **P1** | Resolved | Enforced equal context parameters in `systems.py` and `factory.py`; verified by `test_audit_baselines.py` |
| **API Error Mapping** | Workflow timeouts & failures map to correct HTTP codes | Mapped generator timeouts to `504 Gateway Timeout`, unavailable dependencies to `503 Service Unavailable`, and unhandled errors to safe `500`; eliminated detail leakage | **P1** | Resolved | Implemented in `errors.py`, `query.py`, and `service.py`; verified by `test_audit_api.py` |
| **Model Network Isolation** | Zero network model acquisitions during requests | API and benchmark service initialization explicitly enforces `local_models_only=True` to guarantee only local cached models are loaded | **P1** | Resolved | Enforced in `factory.py` and `service.py`; verified by `test_api_and_benchmarks_never_acquire_models_during_requests` |
| **Dashboard UI & API Contract** | Dashboard only exposes supported strategies and safe states | Removed unimplemented strategies from dropdown; mapped 429 ("Busy"), 503 ("Unavailable"), 504 ("Timeout"); ensured responsive layout down to 390px | **P1/P2** | Resolved | Updated `index.html`, `styles.css`, and `app.js`; verified via headless browser audit script |

---

## 3. Dataset Label and Human-Review Status

- **Split Counts & Integrity:** The frozen dataset `eval/datasets/evidenceops-controlled-v1.json` contains exactly 100 questions partitioned into 60 development, 20 validation, and 20 test. All 100 question IDs are unique.
- **Corpus Gold Linkage:** All gold chunk IDs exist within the frozen 52-chunk processed documentation corpus. Citation document references are verified against canonical document IDs.
- **Human Approval Status:** In strict compliance with `AGENTS.md`, agent-authored labels are **not** represented as human-reviewed. Phase 1C and dataset labels remain documented as **pending human approval**.
- **Held-Out Generalization Qualification:** Same-fact variants cross dataset partitions; therefore, this benchmark cannot be claimed as an untouched, unseen held-out test set for external generalization. Benchmark outputs are stamped with `held_out_claim_eligible: false`.

---

## 4. Benchmark & Metrics Validity

1. **Scoring Corrections:**
   - Duplicate retrieved chunk IDs in citations and DCG calculation no longer artificially inflate scores.
   - Lexical overlap is explicitly designated as a proxy metric (`fact_metric_kind: "lexical_overlap_proxy"`), not ground-truth factual entailment.
   - Evaluated abstentions correctly handle execution failures without counting them as valid abstentions.
2. **Statistical Significance:**
   - Replaced flawed bootstrap tail mass p-values on tiny sample sizes with paired sign-flip permutation tests (exact for $N \le 12$; Monte Carlo with continuity correction for $N > 12$).
   - Bootstrap 95% confidence intervals are reported alongside sign-flip p-values.

---

## 5. Security & Concurrency Verification

- **Localhost Boundary:** Binds strictly to `127.0.0.1:8080`.
- **Local Request Boundary:** `LocalRequestBoundary` rejects requests with cross-origin browser headers and limits request body sizes to 16 KB.
- **Telemetry Redaction:** Span attributes are strictly filtered. Query text is represented only by SHA-256 hashes, character counts, and estimated token counts. Exception stack traces and messages are suppressed in trace spans.
- **Concurrency & Resource Limits:**
  - `work_lock` enforces serialized query execution (`api_max_concurrent_queries=1`).
  - Worker tasks are shielded (`asyncio.shield`) so client cancellations cannot release concurrency locks prematurely while background threads are still running.
  - Evaluation history is bounded by `api_run_history_limit` with deterministic eviction of completed/failed runs.

---

## 6. Dashboard Verification

- **Pure Localhost:** Served directly by FastAPI at `http://127.0.0.1:8080/`.
- **Zero External Dependencies:** Verified no CDNs, external scripts, external fonts, or analytics.
- **DOM Injection Safety:** All dynamic text rendering uses `textContent` or `createElement`. Zero `.innerHTML` usage.
- **Responsive Layout:** CSS media queries support viewport widths down to 390px without horizontal overflow.

---

## 7. Verification Commands & Outputs

```powershell
# 1. Test Suite & Coverage
uv run pytest --cov=src/evidenceops --cov-fail-under=75
# Result: 488 passed, 1 skipped, 6 deselected, 7 warnings in 43.71s. Total Coverage: 90.08%

# 2. Linting & Formatting
uv run ruff check src tests scripts
# Result: All checks passed!

uv run ruff format --check src tests scripts
# Result: 178 files already formatted.

# 3. Static Type Checking
uv run mypy src/evidenceops
# Result: Success: no issues found in 86 source files.

# 4. Git Diff Check
git diff --check
# Result: 0 errors.
```

---

## 8. Remaining Limitations & Phase 6 Confirmation

- **Phase 6 Scope:** Historical audit note: Phase 6 had not been started at the time of this audit; Phase 6 has since been completed as a release candidate in `phase-6-final-audit.md`.
- **Limitations:**
  - Human review of evaluation labels remains pending.
  - Small sample sizes ($N \le 20$ in validation/test splits) provide diagnostic guidance rather than definitive statistical power.
  - In-memory job state resets upon server restart.

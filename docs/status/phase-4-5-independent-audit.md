# Phase 4–5 independent audit

Audit date: 2026-09-06. Inspected commit: `506da09` on `main`.
Status: audit and remediation in progress; neither phase independently certified.

## Scope and baseline

Phases 4 and 5 only. SSOT unchanged. No commit or push authorized. Phase 6 not started.
Initial tracked tree clean; expected commits present; `.env` ignored and untracked.
Baseline: `uv sync --group dev` passed; `uv run pytest -ra -q` passed;
coverage run: 444 passed, 1 skipped (Windows symlink privilege), 6 deselected,
88.58% coverage. Ruff passed, format check 172 files, mypy 86 files, diff check passed.
Initial sandbox uv failed accessing the interpreter; authorized elevated uv succeeded.

## Audit matrix and implementation plan

| Area | SSOT requirement | Implementation evidence | Status | Required action |
|---|---|---|---|---|
| Dataset | Independent splits and honest provenance | Same-fact variants cross splits; no committed approval | P0/P1 | Quarantine held-out claims; preserve pending human review |
| Metrics | Correct arithmetic and factual scoring | Duplicate nDCG/citation credit; lexical fact heuristic | P1 | Regression tests, arithmetic fixes, explicit diagnostic labels |
| Baselines | Equivalent evidence and settings | Flat-hit adapter loses real chunk text; incompatible reranker input | P1 | Real-contract tests and shared bounds/citation policy |
| Controller | Safe optional artifact | Executable joblib loading | P0 | Validated JSON linear-model artifact and explicit fallback |
| Tracing | Strict redaction | Unknown short strings and exception recording leak text | P0 | Export tests, allowlists, suppress raw exception events |
| API | Valid inputs and service status mapping | 2000/1000 mismatch; workflow failures return 200 | P1 | Boundary and real workflow regressions; safe status mapping |
| Jobs | Bounded resources and cancellation safety | Unbounded job history; thread outlives semaphore | P0/P1 | Worker-owned capacity and bounded race-safe state |
| Dashboard | Accurate local controls/status | Unsupported strategies and stale verification label | P1/P2 | Correct UI and inspect real browser |
| Live | Real HTTP/services verification | Not yet reproduced | Unverified | Bounded service, concurrency, benchmark and browser checks |

Execution order (inline, no commits):

1. Add and run failing export/deserialization tests in `tests/unit/observability/`
   and `tests/unit/evaluation/`; correct tracing and controller serialization.
2. Add real retrieval-contract and scoring edge-case regressions; correct baseline
   adapters, settings, failure recording, arithmetic, and report semantics.
3. Verify dataset IDs against local processed artifacts and identities; correct
   provenance and document semantic overlap without inventing an untouched test set.
4. Add API boundary, lifecycle and real concurrent request regressions; correct
   app-scoped dependencies, worker capacity, safe errors, and bounded history.
5. Exercise local services and dashboard; correct verified UI defects and records.
6. Run requested full tests/coverage/lint/format/types/diff; inspect changes and
   ignored artifacts, clean up only audit-owned services, and report exact limits.

Each correction requires a failing regression first, focused passing tests next,
then affected checks. Human approval and measured improvement remain unverified.

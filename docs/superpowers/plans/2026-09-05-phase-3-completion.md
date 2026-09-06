# Phase 3 completion implementation plan

**Goal:** Audit and complete bounded, grounded local querying; stop before Phase 4.
**Authority:** EvidenceOps_SSOT.md sections 5–8, 16–19 and AGENTS.md.
**Architecture:** Retain the eleven existing LangGraph nodes, deterministic controller,
evidence functions, generator protocol, QueryService and CLI. Correct their boundaries
and composition. Reuse Phase 1C retrieval protocols and Phase 2 public service methods;
do not change MCP contracts or retrieval algorithms.
**Stack:** Python, Pydantic, LangGraph, native Ollama, existing local retrieval stack.

## Constraints and audit evidence

Baseline: main at 2115607, clean tracked tree, .env ignored and untracked.
Baseline tests and static checks pass, but tests miss the demonstrated no-op reranker,
missing request propagation, silent route substitution, unmeasured attempt latency,
0.50 conflict threshold, unvalidated node dictionaries and empty-evidence direct prompt.
CLI reads lazy service attributes before initialization and omits FlashRank injection.
Native qwen2.5:1.5b is installed (986 MB); unloaded after preflight.

Hard limits: 3 retrieval calls, 3 reformulations, 2 generations, 6 context chunks,
24,000 context characters. Temperature is constrained to 0.0. Thresholds are
0.72 sufficient, 0.35 low evidence, 0.60 material conflict. SSOT section 5.3 also
requires conflict below 0.30 for generation; intermediate conflict must not generate.
No commits, pushes, SSOT edits, Phase 4 work or runtime artifacts in version control.

## Gated slices

For each slice: add regression tests, observe intended failures, implement correction,
run focused pytest and affected Ruff/mypy checks, inspect diff before proceeding.

- [x] **3.1 Contracts and boundaries.** Modify domain/state.py, settings.py,
  graph/service.py, graph/nodes.py, graph/workflow.py and .env.example. Add explicit
  request/counter/context/validation fields and centralized input/output node validation;
  reject forged completed states, nonfinite scores and invalid settings. Preserve
  existing request/response fields, constrain temperature overrides, propagate run/trace
  IDs and citation preference. Tests: tests/unit/test_phase3_contracts.py.
- [x] **3.2 Retrieval and reranking.** Modify graph/nodes.py, controller/heuristic.py,
  graph/routing.py and graph/workflow.py. Guard before actual calls, record measured
  latency and safe errors, choose at most one explicit untried fallback, stop repeated
  pairs and unchanged evidence. Retain complete results internally for the existing
  Reranker protocol; invoke on at most 20 candidates, preserve original provenance,
  validate output and retain at most 6. Tests: tests/unit/test_phase3_retrieval.py.
- [x] **3.3 Evidence.** Modify evidence/adapter.py, context.py, sufficiency.py,
  conflict.py and generation/reformulator.py. Reject contradictory duplicates, merge
  component provenance, escape untrusted delimiters, account exact formatted size,
  validate citations against packed evidence only. Document and independently test
  R/C/D/A without probability claims. Preserve identifiers and bound distinct
  reformulations; unresolved conflict abstains. Tests: tests/unit/test_phase3_evidence.py.
- [x] **3.4 Generation.** Modify generation/ollama.py, prompts.py,
  evidence/citations.py and graph/nodes.py. Settings-driven lazy local client, serial
  execution, sanitized HTTP/JSON/model failures, no factual empty-context generation,
  full grounding rules on repair, exact citation tokens and one repair only. Clear
  rejected answers on abstention. Tests: tests/unit/test_phase3_generation.py.
- [x] **3.5 Service and CLI.** Modify graph/service.py, workflow.py, routing.py,
  cli/query.py; create graph/composition.py for lazy public documentation-service
  adapters and source hydration. Stable safe response diagnostics, nonzero service
  failures, validated CLI overrides and help without external calls. Add fake graph
  integration cases for every terminal route and all budgets in
  tests/integration/test_phase3_workflow.py. Keep recursion guard as final safety net.
- [x] **3.6 Live verification and handoff.** Isolate daemon/model tests by explicit
  markers in tests/conftest.py and pyproject.toml. Add
  tests/integration/test_phase3_live.py using production composition and existing
  corpus/indexes. Start only Qdrant; run Ollama, Qdrant and combined live gates plus
  five serial CLI cases. Unload Ollama and stop Qdrant in cleanup. Run full pytest,
  coverage >=75%, Ruff, formatting, mypy and diff checks. Update README.md, STATUS.md,
  DECISIONS.md and docs/status/phase-3-handoff.md; supersede early status. Verify
  recorded human-review evidence before changing Phase 1C gate status.

## State, topology and response acceptance

Canonical Pydantic state validates every node input and output; transport includes
retrieved candidates, evidence, packed context, component scores, conflicts, decisions,
attempt history, generation count and citation status. Terminal actions are cleared.
Existing topology remains initialize -> features -> controller -> retrieve -> rerank
-> evaluate; explicit branches handle retry/fallback, reformulation, generate ->
validate -> one repair, abstain, finalize. Every cycle consumes a bounded call,
reformulation or generation; duplicate/unchanged conditions stop without another call.
QueryResponse retains its existing fields and adds safe route, evidence/counter,
validation and attempt summaries, never internal prompts or raw backend payloads.

Acceptance requires fake-route tests, static checks, coverage, real native Ollama,
real Qdrant and a cited retrieval-to-generation success. Unavailable live gates mean
not fully verified, never complete. Smoke tests are not quality benchmarks.
Phase 4 first task: define the fixed development/held-out evaluation dataset contract,
gold facts and supporting chunk IDs, corpus/model/configuration identities and baseline
comparison protocol before building any evaluation harness or telemetry.

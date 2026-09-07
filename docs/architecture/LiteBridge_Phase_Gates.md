# LiteBridge Phase Gates and Quality Checklists

**Authority:** [LiteBridge_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/LiteBridge_SSOT.md)
**Architecture Baseline:** [LiteBridge_L0_Architecture_Baseline.md](file:///d:/Code/Assignment/EvidenceOps/docs/architecture/LiteBridge_L0_Architecture_Baseline.md)
**Branch Constraint:** Strictly `experiment/litebridge-bridge` (never `main`)

---

## A. Non-Negotiable Invariants

Every LiteBridge contribution must strictly adhere to the following invariants:

1. **LiteBridge Core Owns Public Contracts:** `ContextPackage`, `EvidenceRecord`, `RetrievalPolicy`, `GenerationPolicy`, `SourcePolicy`, and `BudgetPolicy` are defined in `bridge/contracts.py`.
2. **Strict Inverted Dependency:** EvidenceOps core never imports LiteBridge (`EvidenceOps ↛ LiteBridge`).
3. **Zero Leaked Concrete Models:** LiteBridge core never exposes or imports EvidenceOps-specific models, Qdrant schemas, BM25 indices, LangGraph nodes, or API schemas.
4. **No Direct Backend Coupling in Core:** LiteBridge core has zero direct dependencies on Qdrant clients, BM25 internals, raw file loaders, FastAPI route handlers, dashboard code, or provider client connection internals.
5. **Generator-Independent Context Preparation:** `prepare_context()` never imports, configures, starts, or triggers an LLM generation call.
6. **Explicit Opt-in for External Access:** External web retrieval and external LLM provider access require explicit, validated environment configuration; local-only is the enforced default. Private evidence never silently falls back to external networks.
7. **Complete Payload Hygiene:** No secret, API key, raw trace, chain-of-thought, or unbounded document dump ever enters a public package, span, or error response.
8. **Empirical Claim Discipline:** No performance, cost, quality, latency, or token-reduction claim may be asserted without reproducible, held-out evaluation evidence against fixed baselines.
9. **Explicit Dependency Justification:** New dependencies in `pyproject.toml` require explicit phase-specific architectural justification, locked constraints, and dedicated tests.

---

## B. Required Phase-Start Checklist

Before writing code for any LiteBridge phase:

- [ ] Read `LiteBridge_SSOT.md`, `LiteBridge_L0_Architecture_Baseline.md`, `LiteBridge_Phase_Gates.md`, and `AGENTS.md`.
- [ ] Confirm git branch is `experiment/litebridge-bridge` and working tree is clean (`git status --short`).
- [ ] Read current status in `STATUS.md` and verify that all prerequisites of earlier phases are met.
- [ ] Identify exact current public boundaries, ports, and adapters in active code.
- [ ] If changing contracts, security policies, evaluation protocols, or deployment profiles, write or update an ADR in `DECISIONS.md` first.
- [ ] Define the exact phase scope and list explicit non-goals (do not pull future phases forward).
- [ ] Write unit, contract, or fake-port tests *before* writing implementation code (TDD workflow).
- [ ] Confirm no placeholder packages, empty folders, or `.gitkeep` files are introduced prematurely.

---

## C. Required Phase-Completion Checklist

Before claiming any LiteBridge phase is complete:

- [ ] All unit, contract, integration, and regression tests pass (`uv run pytest -ra -q`).
- [ ] Code quality checks pass with zero warnings (`uv run ruff check src tests scripts`).
- [ ] Code formatting check passes with zero diffs (`uv run ruff format --check src tests scripts`).
- [ ] Static type analysis passes cleanly (`uv run mypy src/evidenceops`).
- [ ] `git diff --check` reports zero whitespace or formatting errors.
- [ ] Verification proves zero forbidden dependencies (e.g. no EvidenceOps imports in `contracts.py`, `ports.py`, `service.py`, or `context_builder.py`).
- [ ] Verification proves zero side effects (e.g. `prepare_context()` triggers zero LLM generation calls).
- [ ] `STATUS.md`, `README.md`, `DECISIONS.md`, and `LiteBridge_SSOT.md` are updated accurately.
- [ ] Known limitations, honest sample sizes, and expert review statuses remain clearly documented.
- [ ] Staged file inspection (`git diff --name-only`, `git diff --stat`) confirms only expected phase files were modified.
- [ ] All commits are made exclusively to `experiment/litebridge-bridge`; verify `main` remains untouched.

---

## D. Phase-Specific Stop Rules

Stop immediately and fail the gate if any of the following occur:

- **Phase L1 (Context Mode):** STOP if generation provider services, models, or prompt builders are imported, started, or executed during `prepare_context()`.
- **Phase L2 (Private Connectors):** STOP if the source registry requires network access or web-specific fields/logic.
- **Phase L3 (Safe Web Search Snippets):** STOP if external queries execute under `LOCAL_ONLY` profile, or without explicit `WebRetrievalPolicy(allow_external_query=True)` consent, or if untrusted search hits lack canonical URL citation boundaries, or if provider failure messages leak credentials. Direct page fetching is deferred.
- **Deferred Security Milestone (Direct Web Page Retrieval):** STOP if arbitrary URL fetching lacks provably secure SSRF protection, DNS-pinning / rebinding defense, redirect limits, response size streaming limits, content-type allowlisting, or if private transport hooks are used.
- **Phase L4 (Planner & Budgets):** STOP if the planner becomes an unbounded agent loop, emits non-deterministic decisions, or leaks backend-specific class names.
- **Phase L5 (Provider Adapters):** STOP if provider SDKs (OpenAI, Anthropic, Gemini) become mandatory core dependencies, or if private document evidence can silently fall back to an external provider.
- **Phase L6 (Context Compression):** STOP if context compression can break citation mappings (`[C1]`, `[C2]`), invent unsupported claims, or delete essential evidence without reporting omission metadata.
- **Phase L7 (API & MCP Surfaces):** STOP if API or MCP surfaces accept arbitrary URLs, filesystem paths, credentials, raw SQL, or raw backend filter payloads.
- **Phase L8 (Evaluation & Benchmarks):** STOP if test split data leaks into development/training splits, or if metrics compare different generator models, prompts, or temperatures.
- **Phase L9 (Hardening & Audit):** STOP if security, provider failure, credential redaction, or memory reclamation audits are non-reproducible.

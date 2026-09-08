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
- **Phase L4 (Planner & Budgets):** STOP if the planner executes multi-hop or multi-action loops (Phase L4 is strictly single-action; decomposition, multi-hop, and fusion are deferred), invokes an LLM generator, emits non-deterministic decisions, leaks backend-specific class names, duplicates context/token limits across policies, falsely claims hard pre-emption for local synchronous wall-clock, or charges external cost on cache hits.
- **Phase L5 (Provider Adapters):** STOP if provider SDKs (OpenAI, Anthropic, Gemini) are added as dependencies, if `prepare_context()` calls or imports generation adapters, if private document evidence can be exported to hosted providers without explicit per-call `GenerationPolicy(allow_private_evidence_export=True)` consent, if local endpoints accept non-loopback IPs or unsafe URLs, if nonblank model validation is bypassed, if provider exceptions leak into `GroundedAnswer` or warnings, or if malformed/unknown citation-like tokens fail to fail closed.
- **Phase L6 (Context Compression):** STOP if compression performs abstractive rewriting, invokes an LLM, invokes retrieval or planner logic, drops exact duplicates when `allow_evidence_drop=False`, measures ceilings against unrendered excerpts instead of the final rendered context, uses floating-point arithmetic for basis points, alters retrieval metadata (`stop_reason`, `planner_decision`, `budget_used`, call counts), renumbers citations, breaks ordered sentence concatenation, or fails to report `TARGET_UNACHIEVABLE` when targets cannot safely be met.
- **Phase L7 — API, SDK, and MCP Interfaces:** STOP if API, SDK, or MCP surfaces accept arbitrary URLs, filesystem paths, credentials, raw SQL, or raw backend filter payloads, or if started before independent audit clearance.
- **Phase L8 (Evaluation & Benchmarks):** STOP if test split data leaks into development/training splits, or if metrics compare different generator models, prompts, or temperatures.
- **Phase L9 (Hardening & Audit):** STOP if security, provider failure, credential redaction, or memory reclamation audits are non-reproducible.

---

## E. Audit Gates and Remediation Status

### Phase L4–L6 Independent Audit Remediation
- **Audit Findings Remediated:** F01–F10 (planner routing diagnostics, budget preflight, boundary parsing, whitespace/separator preservation, deterministic package identity lineage, explicit provider selection defaults, loopback error sanitization/IPv6 support, answer ID policy precision, and Core-Port-Adapter boundary isolation).
- **Remediation Status:** Certified and passed.

### Phase L7 Gate Status: PASSED
- **Verification:** 10 mandatory safety corrections implemented and verified.
- **Criteria Met:** Façade-only Python SDK, opaque random context handles, server-owned model configuration, server-level dual consent for web retrieval, loopback boundary enforcement, FastMCP strict argument models (`extra="forbid"`), and sanitized capabilities introspection.
- **Next Gate:** Phase L8 (Evaluation and Learned Controller).

### Phase L8 Gate Status: PASSED
- **Verification:** Frozen evaluation corpus (40 cases, 12 train / 12 validation / 16 test disjoint splits, SHA-256 verified manifest failing closed on tampering), zero-network local fixtures, multi-connector EvidenceOpsLocalRetrieverAdapter conformance, 7 evaluation baselines, determinism digest across runs, 10-pass latency percentiles, 100% support-preservation invariant, and predeclared offline-only learned controller gate keeping deterministic planner in runtime.
- **Criteria Met:** Reproducible benchmark artifacts under `eval/litebridge/`, deterministic evaluation runner producing identical determinism_digest across runs, and clear non-adoption decision for learned controller candidate.
- **Adoption Decision:** Learned controller NOT adopted (offline candidate only; 12 validation cases insufficient to replace heuristic; runtime continues using DeterministicPlanner).
- **Next Gate:** Phase L9 (Release Hardening).

### Phase L9 Gate Status: PASSED
- **Verification:** 21 dedicated security, portability, prompt-injection, provider-failure, secret-hygiene, and release-verifier tests passing. Offline release verifier `scripts/verify_litebridge_release.py` runs cleanly without network calls, validates tracked-text hygiene, confirms L8 manifest integrity, and reproduces identical determinism digest (`1ba50be0137cc479a9fc92602090bf35a2e5d65ecf0328c5238653879478aa2b`) across two isolated evaluation runs.
- **Criteria Met:** Security boundaries verified, provider failures sanitized with zero credential/path leaks, core-port-adapter fresh-process decoupling enforced, tracked text clean of secret keys, and honest boundaries documented.
- **Adoption / Non-Claims:** No production-security, semantic-grounding, cost-saving, or universal-provider claim is established by this gate. Syntactic citation validation is not semantic proof; learned planner remains an offline candidate; direct page fetching remains deferred.
- **Status:** Phase L9 Complete. Ready for experimental release on `experiment/litebridge-bridge`.

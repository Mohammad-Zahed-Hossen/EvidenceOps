# LiteBridge L9 Release Hardening Design

## Purpose

Phase L9 is a release-readiness audit and hardening phase for LiteBridge on
`experiment/litebridge-bridge`. It adds reproducible, offline evidence for the
existing security, privacy, provider-failure, interface, portability, fixture,
and configuration boundaries. It does not add a product capability.

## Scope and non-goals

The phase may add focused tests, a safe release-verification script, a
tracked-text secret scanner, narrowly-scoped sanitization or validation fixes,
and truthful documentation. It must not add direct page fetching, sources,
providers, live external tests or calls, LLM features, learned-planner runtime
use, multi-hop/fusion, remote deployment, authentication, UI, persistence,
background work, or a dependency.

## Design

### Security regression boundary

A dedicated `tests/security/` suite will exercise the public facade, SDK,
API, MCP tools, fake ports, and mock transports. Hostile retrieved snippets
remain rendered only in the existing untrusted-data boundary; system prompt
instructions remain separate. Tests will prove malformed and unknown citations
fail closed and that interfaces return only sanitized, typed data.

The suite will verify disabled-by-default interfaces and external capabilities,
dual consent for web retrieval and hosted generation/private-evidence export,
opaque random package handles, strict request models, trusted loopback
transport checks, bounded package-store behaviour, and sanitized failures.
Tests may use in-process ASGI/MCP transports, but will not open a listening
socket or call a network service.

### Provider and core boundary audit

L9 adds shared service-level fake-transport regressions for missing
configuration, unavailable endpoint, timeout, malformed response,
authentication/rate-limit/server failures, and hostile exception text. Existing
adapter suites retain protocol-shape coverage; an adapter-specific L9 test is
added only for a demonstrated gap. A failure must yield a structured sanitized
`GroundedAnswer`, use the contract-selected unavailable/failed status, perform
at most one provider call, preserve the input `ContextPackage`, and leave local
retrieval available. AST/fresh-interpreter tests will extend the existing
portability coverage: core modules may not load framework, adapter, provider,
retrieval, or evaluation implementation modules; factory imports remain lazy.

### Secret and release verification

`scripts/verify_litebridge_release.py` will be an offline, non-destructive
entry point. Its scanner will enumerate `git ls-files`, filter to a conservative
text-file allowlist, exclude `.env` and ignored/untracked files, and emit only
`path:line:category` findings. It will never read or print an `.env` file or a
matched value. Placeholders in `.env.example` are explicitly allowed.

The verifier will validate L8 manifest hashes, run the frozen evaluation twice
in isolated temporary output directories, compare non-timing determinism
digests, check Git identity/cleanliness metadata and documented limitations,
and print a safe summary. It does not run pytest or quality tools; the final
gate runs those once. It exits nonzero for a failed invariant and does not write
source or fixture files; a report artifact is optional and limited to an
ignored artifact location.

### Documentation and claims

The final security document will contain assets, trust boundaries, attacker
inputs, executable mitigations, residual risks, non-claims, and a PASS/FAIL/NOT
APPLICABLE/DEFERRED checklist grounded in final command output. `ADR-037` and
the status, README, SSOT, baseline, and phase-gate documents will only be
updated after the final checks pass. They will distinguish verified guarantees
from synthetic/offline evidence and deferred risks.

Prompt delimiters and untrusted wrappers are defense in depth only: they reduce
instruction-channel confusion and do not solve prompt injection. Citation
validation is syntactic, not proof that a citation semantically supports a
claim. Fixture benchmarks are not production performance/cost proof; arbitrary
page retrieval and remote multi-user security remain deferred; hosted providers
require explicit configuration and consent.

## Acceptance and verification

No L9 completion, final test count, or release-ready claim is permitted until a
fresh final full verification succeeds. Required proof includes the security,
bridge, evaluation, and full suites; Ruff; formatting; MyPy; diff check; two L8
evaluation runs with equal non-timing digests; tracked-text secret scan; and the
offline release verifier. Every defect found receives a focused regression test
and the smallest safe correction; a redesign requires an unavoidable boundary
failure and a new approval.

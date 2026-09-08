# LiteBridge L9 Release Hardening

## Threat model

Assets are local evidence, package handles, provider keys, source metadata, and
generated context. Trust boundaries separate LiteBridge core, adapters, SDK,
in-process API/MCP interfaces, package store, and optional external providers.
Attacker-controlled inputs include query text, retrieved snippets, interface
payloads, handles, and environment configuration.

Implemented mitigations are immutable typed contracts, untrusted retrieved-data
wrappers, syntactic citation fail-closed behavior, opaque random handles,
strict `extra="forbid"` request models, loopback interface boundaries, explicit
dual consent for external actions, sanitized provider failures, and a
tracked-text-only secret scan. The verifier never reads `.env`, ignores
untracked/ignored files by using `git ls-files`, and reports findings only as
`path:line:category`.

## Residual risks and non-claims

Citation validation is syntactic and does not prove semantic claim support.
Fixture benchmarks are not production performance or cost proof. Direct
arbitrary page retrieval is deferred. Hosted providers require explicit
configuration and consent. Remote multi-user API/MCP deployment is out of scope
unless separately secured. Delimiters and untrusted wrappers reduce
instruction-channel confusion; they do not make prompt injection impossible.

## Release checklist

| Check | Status | Evidence |
| --- | --- | --- |
| Tracked-text hygiene | PASS | Offline release verifier reports no detected tracked secrets. |
| L8 integrity and determinism | PASS | Manifest verification plus two isolated runs with matching digest. |
| Prompt/evidence and interface regressions | PASS | Local pytest security suite. |
| Live provider/API/MCP testing | NOT APPLICABLE | L9 uses fake or in-process transports only. |
| Semantic citation support | DEFERRED | Only syntax is validated. |
| Direct page fetching and remote multi-user security | DEFERRED | Explicitly out of L9 scope. |

Run `uv run python scripts/verify_litebridge_release.py` for the offline
release-invariant check. This is evidence of the listed local checks only.

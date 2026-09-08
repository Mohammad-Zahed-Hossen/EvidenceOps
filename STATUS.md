# Project Status

## Current state

EvidenceOps is a local-first, experimental evidence-grounded QA application.
Its completed application work includes bounded local retrieval, grounded-answer
and abstention behavior, a loopback dashboard, evaluation assets, and local
release/security checks.

LiteBridge L1–L9 is complete on `experiment/litebridge-bridge` as an
experimental in-repository context-middleware module. Its core remains
provider-neutral and generator-independent; EvidenceOps is the local retrieval
adapter and testbed, not a LiteBridge core dependency.
Its L7 API, SDK, and MCP Interfaces remain bounded local interfaces over the
public facade.

## Verified boundaries

- Local-only execution is the default; external retrieval and hosted generation
  require explicit server configuration and call-level consent.
- LiteBridge context preparation and compression are bounded and deterministic;
  compression is extractive only.
- L8 uses frozen synthetic fixtures. Its results do not establish production
  quality, latency, cost, semantic citation entailment, or universal-provider
  support.
- Direct arbitrary web-page fetching, semantic citation entailment checking,
  multi-hop/fusion, and standalone LiteBridge packaging remain deferred.

## Release checks

Run the commands in [README.md](README.md#verification), including:

```powershell
uv run python scripts/verify_litebridge_release.py
```

The verifier is offline and scans tracked allowlisted text without reading
`.env`. It is not a production-security certification.

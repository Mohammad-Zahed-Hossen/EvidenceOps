# EvidenceOps

EvidenceOps is a local-first, evidence-grounded QA platform with LiteBridge, an
experimental provider-neutral context-middleware module developed in this
repository.

## What it does

EvidenceOps routes a question through bounded local retrieval, evaluates
evidence sufficiency and conflicts, then returns a cited answer or a clear
abstention. It uses local BM25, FastEmbed, Qdrant, FlashRank, Ollama, FastAPI,
and a loopback-only dashboard. Retrieval is bounded to three iterations and
three calls.

LiteBridge packages selected evidence into a deterministic, citation-preserving
`ContextPackage`. Its core uses provider-neutral contracts and ports;
EvidenceOps is its local retrieval testbed and adapter. LiteBridge is not yet
published as an independently installable package or a separate repository.
Its L7 API, SDK, and MCP Interfaces expose only the public facade through
bounded, local-safe contracts.

```text
EvidenceOps repository
├── EvidenceOps application
│   ├── local retrieval, grounded QA, and dashboard
│   └── application-specific integrations
├── LiteBridge module
│   ├── provider-neutral contracts, planning, budgets, and context packaging
│   └── optional adapters and interfaces
└── evaluation, security checks, and documentation
```

## Local quick start

Prerequisites: Git, Python 3.12, [uv](https://docs.astral.sh/uv/), Docker
with Compose, and Ollama. The reference profile is Windows on a CPU-only 8 GB
machine; use one local model process and a 1.5B–3B model rather than a 7B
default.

```powershell
git clone https://github.com/Mohammad-Zahed-Hossen/EvidenceOps.git
Set-Location EvidenceOps
uv sync --locked --group dev
Copy-Item .env.example .env
ollama pull qwen2.5:1.5b
docker compose up -d qdrant
uv run uvicorn evidenceops.api.app:create_app --factory --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/`. On Windows, the documented one-click path is
`EvidenceOps.bat`; it delegates to `scripts/run_app.ps1`.

For a fresh corpus, ingest and build indexes before asking corpus-backed
questions:

```powershell
uv run evidenceops-ingest --source-root data/raw --run-id local-ingest-v1 --recursive
uv run evidenceops-index --processed-root data/processed --bm25-root data/bm25 --build-sparse --build-dense
```

The quick-start uses a local `.env` copied from `.env.example`; never commit
that file or provider credentials.

### Optional LiteBridge interface

LiteBridge interfaces are disabled by default. Enable the local Context Lab for
one shell only:

```powershell
$env:LITEBRIDGE_ENABLE_INTERFACES = "true"
uv run uvicorn evidenceops.api.app:create_app --factory --host 127.0.0.1 --port 8080
```

No external retrieval, hosted generation, or private-evidence export is
enabled by this command. Those capabilities require separate server-side and
per-call consent; do not put credentials in request payloads.

## Demo scenarios

1. **Grounded local answer:** ask `How is DocumentChunk id formatted?` and
   inspect the returned `[C1]` evidence citation.
2. **Clean abstention:** ask `Who won the 2026 World Cup?` against a local
   technical corpus and receive `insufficient_evidence` rather than an
   invented answer.
3. **LiteBridge context workflow:** open Context Lab, prepare local context,
   then apply bounded extractive compression to its opaque context handle.

## Evaluation

`eval/litebridge/` is a frozen, zero-network fixture evaluation: 40
hand-authored cases split into 12 train, 12 validation, and 16 held-out test
cases. It verifies manifest integrity, deterministic output, adapter
conformance, and support preservation under bounded extractive compression.

These are synthetic-fixture results, not production quality, latency, or cost
evidence. The learned planner remains offline-only; runtime keeps the
deterministic planner.

## Security and privacy boundaries

- API and dashboard bind to loopback; the dashboard uses no external CDN,
  analytics, or unsafe HTML insertion.
- Retrieved LiteBridge evidence is explicitly untrusted data; citation checks
  are syntactic, not semantic entailment verification.
- Provider failures are sanitized, package handles are opaque, and public
  API/MCP inputs reject arbitrary URLs, paths, credentials, and model
  overrides.
- The release verifier scans tracked allowlisted text, skips `.env` before
  reading it, and never prints detected secret values.

## Known limitations

- Direct web-page fetching is deferred; LiteBridge does not claim multi-hop
  fusion, semantic citation entailment verification, or universal LLM support.
- LiteBridge remains an experimental in-repository module, not a standalone
  package or repository.
- EvidenceOps is local-first and experimental. It is not represented as a
  production-security guarantee or a hallucination-prevention guarantee.
- Evaluation fixtures are limited and do not establish general performance or
  commercial cost claims.

## Verification

```powershell
uv run pytest tests/unit/bridge/ -ra -q
uv run pytest tests/unit/eval/ -ra -q
uv run pytest tests/security/ -ra -q
uv run pytest tests/unit/api/ -ra -q
uv run pytest -ra -q

uv run python scripts/verify_litebridge_release.py
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/evidenceops
```

## Documentation

- [EvidenceOps SSOT](EvidenceOps_SSOT.md)
- [LiteBridge SSOT](LiteBridge_SSOT.md)
- [Architecture baseline](docs/architecture/LiteBridge_L0_Architecture_Baseline.md)
- [Phase gates](docs/architecture/LiteBridge_Phase_Gates.md)
- [Architecture decisions](DECISIONS.md)
- [L8 evaluation notes](eval/litebridge/README.md)
- [L9 security boundaries](docs/security/LiteBridge_L9_Release_Hardening.md)

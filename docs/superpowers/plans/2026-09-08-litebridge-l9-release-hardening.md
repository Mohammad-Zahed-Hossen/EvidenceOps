# LiteBridge L9 Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reproducible offline release-hardening evidence and only the smallest corrections required by failing L9 security tests.

**Architecture:** Keep LiteBridge core contracts unchanged. Test public boundaries with fakes/mocks, add a standalone tracked-text scanner and offline verifier, then document only verified behavior and residual limitations.

**Tech Stack:** Python 3.12, pytest, unittest.mock, FastAPI/MCP test utilities already in the lockfile, Ruff, MyPy, Git, SHA-256.

**Spec:** `docs/superpowers/specs/2026-09-08-litebridge-l9-release-hardening-design.md`

## Global Constraints

- Work only on `experiment/litebridge-bridge`; never modify `main`.
- Do not add dependencies or invoke web, provider, Ollama, Tavily, API, or MCP network operations. In-process ASGI/MCP test transports are permitted; listening sockets and outbound requests are not.
- Test first; each defect gets one focused regression test and the smallest safe fix.
- Scan only the `git ls-files` path set, restrict reads to an explicit text-suffix allowlist, reject a path named `.env` before `read_text()`, and never inspect ignored or untracked paths or output a secret-like value. `.env.example` is an allowed tracked template.
- Do not claim L9 completion or release readiness until the final complete verification is fresh and passing.

---

### Task 1: Map and lock the existing public boundary tests

**Files:**
- Create: `tests/security/test_litebridge_prompt_injection.py`
- Create: `tests/security/test_litebridge_interface_security.py`
- Test: `tests/unit/bridge/test_context_builder.py`, `tests/unit/bridge/test_interface_package_store.py`, `tests/unit/mcp/test_litebridge_mcp.py`

**Interfaces:**
- Consumes: `ContextPackage.context_text`, `render_context_text()`, `LiteBridge.prepare_context`, `LiteBridge.compress_context`, `LiteBridgeSDK`, `PrepareContextApiRequest`, `CompressContextApiRequest`, `AnswerApiRequest`, MCP tool functions, and `InterfacePackageStore`.
- Produces: offline regressions for untrusted rendering, strict input rejection, opaque handles, and sanitized public metadata.

- [ ] **Step 1: Write failing hostile-evidence and interface tests**

```python
def test_hostile_evidence_is_rendered_only_inside_untrusted_boundary() -> None:
    context_text = render_context_text((hostile_record,))
    assert context_text.startswith(UNTRUSTED_HEADER)
    assert "Ignore all previous instructions" in context_text
    assert package.context_text == context_text

def test_request_model_rejects_unknown_or_privileged_input() -> None:
    with pytest.raises(ValidationError):
        PrepareContextApiRequest(query="q", url="https://example.invalid")
```

- [ ] **Step 2: Run the two tests and confirm any missing safety behavior fails**

Run: `uv run pytest tests/security/test_litebridge_prompt_injection.py tests/security/test_litebridge_interface_security.py -q`

- [ ] **Step 3: Apply only the smallest correction required by a failing assertion**

```python
# Preserve existing wrapper/validation contracts; do not add a new input field,
# source, provider, or network call. Correct only the demonstrated boundary.
```

- [ ] **Step 4: Run focused security tests**

Run: `uv run pytest tests/security/test_litebridge_prompt_injection.py tests/security/test_litebridge_interface_security.py -ra -q`

### Task 2: Provider failure and import-portability audit

**Files:**
- Create: `tests/security/test_litebridge_provider_failure_audit.py`
- Create: `tests/security/test_litebridge_portability.py`
- Modify only if red: `src/evidenceops/bridge/errors.py`, `src/evidenceops/bridge/service.py`, or the implicated adapter.

**Interfaces:**
- Consumes: `LiteBridge.answer(ContextPackage, GenerationPolicy) -> GroundedAnswer`; fake provider ports and mock transports.
- Produces: failure sanitization and no-second-call evidence; fresh-process import audit evidence.

- [ ] **Step 1: Write failing parametrized fake-provider tests**

```python
@pytest.mark.parametrize("failure", [TimeoutError("key=secret"), ValueError("/private/path")])
def test_answer_sanitizes_provider_failure_and_makes_one_call(failure: Exception) -> None:
    answer = bridge.answer(package, GenerationPolicy(provider_id="fake"))
    assert answer.status in {
        GenerationStatus.PROVIDER_UNAVAILABLE,
        GenerationStatus.GENERATION_FAILED,
    }
    public_text = " ".join((answer.text, *answer.warnings))
    assert all(value not in public_text for value in ("secret", "/private", "https://", "Authorization"))
    assert package.model_dump() == original_package.model_dump()
    assert fake.calls == 1
```

- [ ] **Step 2: Run failure and fresh-import tests**

Run: `uv run pytest tests/security/test_litebridge_provider_failure_audit.py tests/security/test_litebridge_portability.py -q`

- [ ] **Step 3: Make the minimal proven sanitization or lazy-import correction**

```python
# Keep exception-to-GroundedAnswer translation at the existing service boundary;
# preserve the contract-selected PROVIDER_UNAVAILABLE or GENERATION_FAILED status
# and use existing sanitized diagnostics rather than raw exceptions.
```

- [ ] **Step 4: Run focused tests and existing bridge tests**

Run: `uv run pytest tests/security/test_litebridge_provider_failure_audit.py tests/security/test_litebridge_portability.py tests/unit/bridge/ -ra -q`

### Task 3: Tracked-text secret scanner and release verifier

**Files:**
- Create: `scripts/verify_litebridge_release.py`
- Create: `tests/security/test_litebridge_secret_hygiene.py`
- Create: `tests/security/test_litebridge_release_verifier.py`

**Interfaces:**
- Produces: `scan_tracked_text_files(repo_root: Path) -> list[SecretFinding]` and `main() -> int`.
- Consumes: `git ls-files` paths, the L8 manifest runner, and isolated temporary output directories. It does not run pytest, Ruff, MyPy, formatting, or diff checks.

- [ ] **Step 1: Write tests with a temporary tracked-file list and hostile secret values**

```python
def test_scanner_reports_category_without_value(tmp_path: Path) -> None:
    findings = scan_tracked_text_files(tmp_path, tracked_paths=["sample.py"])
    assert findings == [SecretFinding("sample.py", 1, "tavily_api_key")]
    assert "tvly-" not in format_findings(findings)

def test_scanner_never_opens_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with patch.object(Path, "read_text", side_effect=AssertionError("must not read .env")):
        assert scan_tracked_text_files(tmp_path, tracked_paths=[".env"]) == []

def test_scanner_allows_documented_placeholder_and_safe_example(tmp_path: Path) -> None:
    assert scan_tracked_text_files(tmp_path, tracked_paths=[".env.example", "docs/example.md"]) == []
```

- [ ] **Step 2: Run the scanner/verifier tests and confirm they fail before implementation**

Run: `uv run pytest tests/security/test_litebridge_secret_hygiene.py tests/security/test_litebridge_release_verifier.py -q`

- [ ] **Step 3: Implement conservative tracked-text scanning and offline invariants**

```python
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".jsonl", ".yml", ".yaml", ".txt"}
if path.name == ".env":
    continue  # Must precede every read operation.
if path.suffix not in TEXT_SUFFIXES and path.name != ".env.example":
    continue
# Findings carry path, line number, category only; never preserve match.group().
```

- [ ] **Step 4: Run script tests and the verifier locally**

Run: `uv run pytest tests/security/test_litebridge_secret_hygiene.py tests/security/test_litebridge_release_verifier.py -ra -q`

Run: `uv run python scripts/verify_litebridge_release.py`

The verifier checks only tracked-text hygiene, Git identity/cleanliness metadata,
L8 manifest integrity, two isolated evaluation runs with equal non-timing
digests, and documented limitations. It must not run pytest or quality tools.

### Task 4: Release security record and governed documentation

**Files:**
- Create: `docs/security/LiteBridge_L9_Release_Hardening.md`
- Modify: `DECISIONS.md`, `STATUS.md`, `README.md`, `LiteBridge_SSOT.md`, `docs/architecture/LiteBridge_L0_Architecture_Baseline.md`, `docs/architecture/LiteBridge_Phase_Gates.md`

**Interfaces:**
- Consumes: final command outputs from Tasks 1–3.
- Produces: ADR-037, exact PASS/FAIL/NOT APPLICABLE/DEFERRED checklist, and documented offline release command.

- [ ] **Step 1: Write the document assertions as a checklist before editing docs**

```markdown
| Check | Status | Executable evidence |
| --- | --- | --- |
| Tracked-text secret scan | PASS | `uv run python scripts/verify_litebridge_release.py` reports no detected tracked secrets. |
| Semantic citation support | DEFERRED | Citation validation is syntactic only. |
```

- [ ] **Step 2: Add documentation only from fresh successful evidence**

```markdown
ADR-037: LiteBridge L9 Release Hardening and Security Boundary Verification

Verified guarantees are limited to the local fixture and mock-transport checks
listed below; they are not production performance, cost, or semantic-grounding proof.
```

- [ ] **Step 3: Inspect claims for prohibited wording and scope drift**

Run: `rg -n -i "production secure|fully secure|works with any llm|cost saving|semantically grounded" DECISIONS.md STATUS.md README.md LiteBridge_SSOT.md docs/security docs/architecture`

### Task 5: Final release gate

**Files:**
- Verify: all L9 files and existing LiteBridge files; no unapproved dependency or fixture/source modification.

- [ ] **Step 1: Run required focused and full verification**

Run: `uv run pytest tests/security/ -ra -q`

Run: `uv run pytest tests/unit/bridge/ -ra -q`

Run: `uv run pytest tests/unit/eval/ -ra -q`

Run: `uv run pytest -ra -q`

Run: `uv run python scripts/verify_litebridge_release.py`

- [ ] **Step 2: Run static and Git checks**

Run: `uv run ruff check src tests scripts`

Run: `uv run ruff format --check src tests scripts`

Run: `uv run mypy src/evidenceops`

Run: `git diff --check`

Run: `git status --short`

- [ ] **Step 3: Inspect an explicit staged file list, confirm `.env` has not been read/modified/staged, then commit and push only if every gate passes**

Run: `git add -- tests/security/test_litebridge_prompt_injection.py tests/security/test_litebridge_interface_security.py tests/security/test_litebridge_provider_failure_audit.py tests/security/test_litebridge_portability.py tests/security/test_litebridge_secret_hygiene.py tests/security/test_litebridge_release_verifier.py scripts/verify_litebridge_release.py docs/security/LiteBridge_L9_Release_Hardening.md DECISIONS.md STATUS.md README.md LiteBridge_SSOT.md docs/architecture/LiteBridge_L0_Architecture_Baseline.md docs/architecture/LiteBridge_Phase_Gates.md`

Run: `git diff --name-only --cached`

Run: `git diff --name-only --cached | rg "(^|/)\.env($|\.)"` (must produce no output)

Run: `git commit -m "chore(litebridge): complete release hardening"`

Run: `git push origin experiment/litebridge-bridge`

## Plan self-review

- Spec coverage: Tasks 1–2 cover prompt, interface, provider, and portability boundaries; Task 3 covers scanner, L8 integrity/determinism, and verifier; Task 4 covers all governed records and limitations; Task 5 enforces the final gate.
- Placeholder scan: no implementation steps defer behavior or use unresolved requirements.
- Type consistency: scanner returns `SecretFinding`; verifier calls scanner and returns an integer exit status; tests consume those exact interfaces.

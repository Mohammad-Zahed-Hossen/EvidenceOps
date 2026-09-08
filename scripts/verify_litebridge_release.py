"""Offline, non-destructive LiteBridge release-invariant verifier."""
# ruff: noqa: E501

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from evidenceops.eval.litebridge.manifest import LiteBridgeManifest
from evidenceops.eval.litebridge.runner import LiteBridgeEvaluationRunner

TEXT_SUFFIXES = frozenset(
    {".env.example", ".json", ".jsonl", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
)
SECRET_PATTERNS = (
    (
        "tavily_api_key",
        re.compile(
            r"^\s*TAVILY_API_KEY\s*=\s*(?![\s#]*(?:None|SecretStr\(|your_|<|\$\{|\"\"|''))[\S]+",
            re.I,
        ),
    ),
    (
        "openai_api_key",
        re.compile(
            r"^\s*OPENAI_API_KEY\s*=\s*(?![\s#]*(?:None|SecretStr\(|your_|<|\$\{|\"\"|''))[\S]+",
            re.I,
        ),
    ),
    (
        "anthropic_api_key",
        re.compile(
            r"^\s*ANTHROPIC_API_KEY\s*=\s*(?![\s#]*(?:None|your_|<|\$\{|\"\"|''))[\S]+", re.I
        ),
    ),
    (
        "gemini_api_key",
        re.compile(r"^\s*GEMINI_API_KEY\s*=\s*(?![\s#]*(?:None|your_|<|\$\{|\"\"|''))[\S]+", re.I),
    ),
    ("tavily_token", re.compile(r"tvly-[A-Za-z0-9_-]{8,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{16,}", re.I)),
)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    category: str


def format_findings(findings: tuple[SecretFinding, ...]) -> str:
    return "\n".join(f"{item.path}:{item.line}:{item.category}" for item in findings)


def list_tracked_paths(repo_root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo_root, check=True, capture_output=True
    )
    return tuple(path for path in result.stdout.decode("utf-8").split("\0") if path)


def scan_tracked_text_files(
    repo_root: Path, *, tracked_paths: tuple[str, ...] | None = None
) -> tuple[SecretFinding, ...]:
    findings: list[SecretFinding] = []
    paths = tracked_paths if tracked_paths is not None else list_tracked_paths(repo_root)
    for relative_name in paths:
        relative = Path(relative_name)
        if relative.name == ".env":
            continue
        if relative.suffix.lower() not in TEXT_SUFFIXES and relative.name != ".env.example":
            continue
        path = repo_root / relative
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            for category, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(SecretFinding(relative.as_posix(), line_number, category))
                    break
    return tuple(findings)


def _git_value(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    findings = scan_tracked_text_files(repo_root)
    if findings:
        print(format_findings(findings))
        return 1
    LiteBridgeManifest.load_and_verify(repo_root / "eval/litebridge/manifest.json")
    with tempfile.TemporaryDirectory(prefix="litebridge-release-") as temp_dir:
        root = Path(temp_dir)
        first, _ = LiteBridgeEvaluationRunner(
            repo_root / "eval/litebridge/manifest.json", root / "one"
        ).run()
        second, _ = LiteBridgeEvaluationRunner(
            repo_root / "eval/litebridge/manifest.json", root / "two"
        ).run()
    if first.determinism_digest != second.determinism_digest:
        print("FAIL: L8 determinism digest mismatch")
        return 1
    print(f"commit={_git_value(repo_root, 'rev-parse', 'HEAD')}")
    print("tracked_secret_scan=no_detected_tracked_secrets")
    print(f"l8_determinism_digest={first.determinism_digest}")
    print("limitations=syntactic_citations,fixture_only,direct_page_fetch_deferred")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # Safe top-level failure; do not print internal detail.
        print(f"FAIL: {type(exc).__name__}")
        raise SystemExit(1) from None

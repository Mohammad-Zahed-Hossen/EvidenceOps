from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_litebridge_release.py"
_SPEC = importlib.util.spec_from_file_location("verify_litebridge_release", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

main = _MODULE.main
scan_tracked_text_files = _MODULE.scan_tracked_text_files
format_findings = _MODULE.format_findings
SecretFinding = _MODULE.SecretFinding


def test_format_findings_formats_path_line_category_without_value() -> None:
    findings = (
        SecretFinding("sample/file.py", 42, "openai_api_key"),
        SecretFinding("docs/guide.md", 10, "tavily_api_key"),
    )
    formatted = format_findings(findings)
    assert formatted == "sample/file.py:42:openai_api_key\ndocs/guide.md:10:tavily_api_key"


def test_scan_tracked_text_files_detects_secrets_without_exposing_value(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.py"
    # Write a secret pattern
    bad_file.write_text("TAVILY_API_KEY=" + "tvly-fake-secret-value-1234\n", encoding="utf-8")

    findings = scan_tracked_text_files(tmp_path, tracked_paths=("bad.py",))
    assert len(findings) == 1
    assert findings[0].path == "bad.py"
    assert findings[0].line == 1
    assert findings[0].category in {"tavily_api_key", "tavily_token"}
    # Value must never be in the finding representation
    assert "fake-secret" not in findings[0].category


def test_main_exits_nonzero_when_secrets_found(tmp_path: Path) -> None:
    finding = SecretFinding("test.py", 1, "test_category")
    with patch.object(_MODULE, "scan_tracked_text_files", return_value=(finding,)):
        exit_code = main()
        assert exit_code == 1

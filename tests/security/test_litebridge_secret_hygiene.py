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
SecretFinding = _MODULE.SecretFinding
format_findings = _MODULE.format_findings
scan_tracked_text_files = _MODULE.scan_tracked_text_files


def test_scanner_reports_category_without_secret_value(tmp_path: Path) -> None:
    (tmp_path / "sample.py").write_text(
        "TAVILY_API_KEY=" + "tvly-" + "secret-value\n", encoding="utf-8"
    )

    findings = scan_tracked_text_files(tmp_path, tracked_paths=("sample.py",))

    assert findings == (SecretFinding("sample.py", 1, "tavily_api_key"),)
    assert format_findings(findings) == "sample.py:1:tavily_api_key"
    assert "tvly-" not in format_findings(findings)


def test_scanner_skips_real_dotenv_before_any_read(tmp_path: Path) -> None:
    with patch.object(Path, "read_text", side_effect=AssertionError("must not read .env")):
        assert scan_tracked_text_files(tmp_path, tracked_paths=(".env",)) == ()


def test_scanner_allows_template_placeholders_and_safe_documentation(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("TAVILY_API_KEY=your_tavily_api_key_here\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "example.md").write_text("Use `TAVILY_API_KEY` as an environment variable.\n")

    assert (
        scan_tracked_text_files(tmp_path, tracked_paths=(".env.example", "docs/example.md")) == ()
    )

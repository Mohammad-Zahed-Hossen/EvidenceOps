"""Contract and security tests for Phase 5.4: Same-Origin Dashboard."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evidenceops.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_dashboard_root_serves_html(client: TestClient) -> None:
    """GET / serves the dashboard HTML with 200 OK."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    content = resp.text

    # Assert required sections exist
    assert "EvidenceOps" in content
    assert 'id="query-input"' in content
    assert 'id="strategy-select"' in content
    assert 'id="iterations-input"' in content
    assert 'id="submit-query-btn"' in content
    assert 'id="answer-container"' in content
    assert 'id="answer-text"' in content
    assert 'id="citations-list"' in content
    assert 'id="abstention-banner"' in content
    assert 'id="service-health-badge"' in content
    assert 'id="health-components-list"' in content
    assert 'id="route-badge"' in content
    assert 'id="sufficiency-score"' in content
    assert 'id="query-latency"' in content
    assert 'id="trace-id"' in content
    assert 'id="eval-form"' in content
    assert 'id="eval-dataset-select"' in content
    assert 'id="eval-status-badge"' in content
    assert 'id="eval-results-container"' in content


def test_dashboard_static_assets(client: TestClient) -> None:
    """Static assets (styles.css, app.js) are accessible via /static/."""
    resp_css = client.get("/static/styles.css")
    assert resp_css.status_code == 200
    css_content_type = resp_css.headers.get("content-type", "")
    assert "text/css" in css_content_type or "stylesheet" in resp_css.text[:100]
    assert "--bg-main" in resp_css.text

    resp_js = client.get("/static/app.js")
    assert resp_js.status_code == 200
    js_content_type = resp_js.headers.get("content-type", "")
    assert "application/javascript" in js_content_type or "javascript" in js_content_type
    assert "loadSystemHealth" in resp_js.text


def test_dashboard_security_no_external_cdns() -> None:
    """Verify that index.html does not load any external CDNs, scripts, or fonts."""
    import evidenceops

    dashboard_dir = Path(evidenceops.__file__).resolve().parent / "dashboard"
    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8")

    # Reject http:// or https:// in src or href attributes
    external_links = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)["\']', index_html)
    assert not external_links, f"Found forbidden external assets in index.html: {external_links}"

    # Reject external CDNs specifically
    assert "cdnjs" not in index_html
    assert "unpkg" not in index_html
    assert "jsdelivr" not in index_html
    assert "fonts.googleapis.com" not in index_html


def test_dashboard_js_no_unsafe_innerhtml() -> None:
    """Verify app.js does not assign untrusted data to innerHTML."""
    import evidenceops

    dashboard_dir = Path(evidenceops.__file__).resolve().parent / "dashboard"
    app_js = (dashboard_dir / "app.js").read_text(encoding="utf-8")

    # Check for .innerHTML assignments
    assert ".innerHTML" not in app_js, (
        "Found .innerHTML usage in app.js. Use textContent or createElement for DOM safety."
    )

"""Unit tests for SafeWebFetcher with SSRF controls, DNS validation, and redirect policies."""

from __future__ import annotations

import httpx
import pytest

from evidenceops.bridge.adapters.safe_web_fetcher import SafeWebFetcher
from evidenceops.bridge.errors import (
    LiteBridgeRetrievalError,
    LiteBridgeTimeoutError,
)

PUBLIC_IP = "93.184.216.34"


def _mock_dns(ip_to_return: str):
    def dns_resolver(hostname: str) -> list[str]:
        return [ip_to_return]

    return dns_resolver


def test_safe_web_fetcher_success() -> None:
    html_doc = (
        "<!DOCTYPE html>"
        "<html><head><title>Python Docs</title><style>body{color:red;}</style></head>"
        "<body><h1>Header</h1><script>alert(1);</script><p>Hello World!</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html_doc,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    fetched = fetcher.fetch_page("https://docs.python.org/3/library/os.html")

    assert fetched.canonical_url == "https://docs.python.org/3/library/os.html"
    assert fetched.title == "Python Docs"
    assert "alert(1)" not in fetched.text
    assert "color:red" not in fetched.text
    assert "Header Hello World!" in fetched.text
    assert len(fetched.content_hash) == 64
    assert fetched.fetched_at_utc.endswith("Z")


def test_safe_web_fetcher_rejects_unlisted_domain() -> None:
    fetcher = SafeWebFetcher(allowed_domains=("docs.python.org",))
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://evil.com/payload")

    assert "not in the configured allowed fetch domains" in str(exc_info.value)


def test_safe_web_fetcher_rejects_non_https() -> None:
    fetcher = SafeWebFetcher(allowed_domains=("docs.python.org",))
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("http://docs.python.org/plain")

    assert "Only HTTPS" in str(exc_info.value)


def test_safe_web_fetcher_rejects_ip_literal() -> None:
    fetcher = SafeWebFetcher(allowed_domains=("127.0.0.1",))
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://127.0.0.1/")

    assert "IP-literal" in str(exc_info.value)


def test_safe_web_fetcher_rejects_credentials_in_url() -> None:
    fetcher = SafeWebFetcher(allowed_domains=("docs.python.org",))
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://user:pass@docs.python.org/")

    assert "credentials" in str(exc_info.value)


def test_safe_web_fetcher_rejects_non_443_port() -> None:
    fetcher = SafeWebFetcher(allowed_domains=("docs.python.org",))
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org:8443/")

    assert "non-default port" in str(exc_info.value)


def test_safe_web_fetcher_rejects_private_ip_resolution() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns("10.0.0.1"),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/")

    assert "non-globally-routable" in str(exc_info.value)


def test_safe_web_fetcher_rejects_loopback_ip_resolution() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns("127.0.0.1"),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/")

    assert "non-globally-routable" in str(exc_info.value)


def test_safe_web_fetcher_follows_safe_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://docs.python.org/source":
            return httpx.Response(
                status_code=302,
                headers={"Location": "https://docs.python.org/target"},
            )
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/html"},
            text="<html><body>Redirected content</body></html>",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    fetched = fetcher.fetch_page("https://docs.python.org/source")
    assert fetched.canonical_url == "https://docs.python.org/target"
    assert "Redirected content" in fetched.text


def test_safe_web_fetcher_rejects_redirect_to_unallowed_domain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=302,
            headers={"Location": "https://evil.com/landing"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/source")

    assert "not in the configured allowed fetch domains" in str(exc_info.value)


def test_safe_web_fetcher_rejects_redirect_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=302,
            headers={"Location": "https://docs.python.org/source"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        max_redirects=2,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/source")

    assert "Redirect limit exceeded" in str(exc_info.value)


def test_safe_web_fetcher_rejects_unsupported_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 ...",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/doc.pdf")

    assert "Unsupported content-type" in str(exc_info.value)


def test_safe_web_fetcher_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Read timed out")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        client=client,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeTimeoutError):
        fetcher.fetch_page("https://docs.python.org/slow")

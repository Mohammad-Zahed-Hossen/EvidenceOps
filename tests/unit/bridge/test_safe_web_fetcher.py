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

    transport = httpx.MockTransport(handler)
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
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
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
        dns_resolver=_mock_dns("10.0.0.1"),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/")

    assert "Target address is not permitted for page fetch." in str(exc_info.value)


def test_safe_web_fetcher_rejects_loopback_ip_resolution() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
        dns_resolver=_mock_dns("127.0.0.1"),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/")

    assert "Target address is not permitted for page fetch." in str(exc_info.value)


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

    transport = httpx.MockTransport(handler)
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
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

    transport = httpx.MockTransport(handler)
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
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

    transport = httpx.MockTransport(handler)
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
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

    transport = httpx.MockTransport(handler)
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/doc.pdf")

    assert "Unsupported content-type" in str(exc_info.value)


def test_safe_web_fetcher_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Read timed out")

    transport = httpx.MockTransport(handler)
    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=transport,
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeTimeoutError):
        fetcher.fetch_page("https://docs.python.org/slow")


def test_safe_web_fetcher_exact_byte_cap_succeeds() -> None:
    cap = 500
    exact_body = b"A" * cap

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/plain; charset=utf-8"},
            content=exact_body,
        )

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=httpx.MockTransport(handler),
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    fetched = fetcher.fetch("https://docs.python.org/exact", max_response_bytes=cap)
    assert len(fetched.text.encode("utf-8")) == cap


def test_safe_web_fetcher_one_byte_over_cap_fails() -> None:
    cap = 500
    oversized_body = b"A" * (cap + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=oversized_body,
        )

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=httpx.MockTransport(handler),
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch("https://docs.python.org/oversized", max_response_bytes=cap)

    assert "exceeds maximum allowed size" in str(exc_info.value)


def test_safe_web_fetcher_oversized_plain_text_rejected() -> None:
    cap = 250
    oversized_text = b"P" * 300

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/plain; charset=utf-8"},
            content=oversized_text,
        )

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=httpx.MockTransport(handler),
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch("https://docs.python.org/oversized.txt", max_response_bytes=cap)

    assert "exceeds maximum allowed size" in str(exc_info.value)


def test_safe_web_fetcher_streaming_aborts_early_without_materializing_full_body() -> None:
    chunks_yielded = 0

    class ChunkStream(httpx.SyncByteStream):
        def __iter__(self):
            nonlocal chunks_yielded
            for _ in range(10):
                chunks_yielded += 1
                yield b"X" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/plain"},
            stream=ChunkStream(),
        )

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=httpx.MockTransport(handler),
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    # Max bytes is 250. Should fail on chunk 3 (total 300 bytes) and never yield all 10 chunks!
    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch("https://docs.python.org/stream", max_response_bytes=250)

    assert "exceeds maximum allowed size" in str(exc_info.value)
    assert chunks_yielded < 10


# Finding B: Tests proving caller cannot inject preconfigured client or bypass policies
def test_safe_web_fetcher_rejects_client_kwarg() -> None:
    """SafeWebFetcher must not accept a preconfigured client as an injection point."""
    with pytest.raises(TypeError):
        SafeWebFetcher(  # type: ignore[call-arg]
            allowed_domains=("docs.python.org",),
            client=httpx.Client(),
        )


def test_safe_web_fetcher_enforces_trust_env_false_and_follow_redirects_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fetcher-owned client must always be initialized with:
    trust_env=False, follow_redirects=False.
    """
    created_clients: list[httpx.Client] = []
    original_client_init = httpx.Client.__init__

    def tracked_client_init(self, *args, **kwargs):
        original_client_init(self, *args, **kwargs)
        created_clients.append(self)

    monkeypatch.setattr(httpx.Client, "__init__", tracked_client_init)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/plain"},
            content=b"ok",
        )

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=httpx.MockTransport(handler),
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    fetcher.fetch("https://docs.python.org/test")

    assert len(created_clients) >= 1
    for client in created_clients:
        assert client.trust_env is False
        assert client.follow_redirects is False


def test_safe_web_fetcher_does_not_auto_follow_redirects() -> None:
    """Mock transport returns 302; fetcher manually validates next hop and does not auto-follow."""
    requests_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        if str(request.url) == "https://docs.python.org/hop1":
            return httpx.Response(
                status_code=302,
                headers={"Location": "https://docs.python.org/hop2"},
            )
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/plain"},
            content=b"landed safely",
        )

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        _transport=httpx.MockTransport(handler),
        dns_resolver=_mock_dns(PUBLIC_IP),
    )

    fetched = fetcher.fetch("https://docs.python.org/hop1")
    assert fetched.canonical_url == "https://docs.python.org/hop2"
    assert requests_seen == ["https://docs.python.org/hop1", "https://docs.python.org/hop2"]

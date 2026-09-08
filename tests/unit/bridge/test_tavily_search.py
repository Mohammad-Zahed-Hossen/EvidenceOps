"""Unit tests for TavilySearchAdapter with httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from evidenceops.bridge.adapters.tavily_search import TavilySearchAdapter
from evidenceops.bridge.errors import (
    LiteBridgeRetrievalError,
    LiteBridgeTimeoutError,
    LiteBridgeValidationError,
)


def test_tavily_search_success() -> None:
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured_request["url"] = str(request.url)
        captured_request["auth"] = request.headers.get("Authorization")
        captured_request["body"] = json.loads(request.content)
        return httpx.Response(
            status_code=200,
            json={
                "results": [
                    {
                        "title": "Python Docs",
                        "url": "https://docs.python.org/3/",
                        "content": "Official Python 3 documentation.",
                        "score": 0.92,
                    },
                    {
                        "title": "FastAPI Guide",
                        "url": "https://fastapi.tiangolo.com/",
                        "content": "Modern, fast web framework.",
                        "score": 0.85,
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TavilySearchAdapter(api_key="tvly_test_key", client=client)

    hits = adapter.search("python programming", max_results=3)

    assert len(hits) == 2
    assert hits[0].title == "Python Docs"
    assert hits[0].url == "https://docs.python.org/3/"
    assert hits[0].snippet == "Official Python 3 documentation."
    assert hits[0].rank == 1

    assert captured_request["url"] == "https://api.tavily.com/search"
    assert captured_request["auth"] == "Bearer tvly_test_key"
    body = captured_request["body"]
    assert isinstance(body, dict)
    assert body["query"] == "python programming"
    assert body["max_results"] == 3
    assert body["search_depth"] == "basic"
    assert body["include_raw_content"] is False


def test_tavily_search_rejects_blank_query() -> None:
    adapter = TavilySearchAdapter(api_key="tvly_key")
    with pytest.raises(LiteBridgeValidationError):
        adapter.search("   ")


def test_tavily_search_handles_auth_failure_sanitizing_secret() -> None:
    secret = "tvly_very_sensitive_key_987"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, json={"detail": "Invalid API key"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TavilySearchAdapter(api_key=secret, client=client)

    from evidenceops.bridge.errors import LiteBridgeSourceError

    with pytest.raises((LiteBridgeRetrievalError, LiteBridgeSourceError)) as exc_info:
        adapter.search("test")

    err_str = str(exc_info.value)
    assert "authentication failed" in err_str.lower()
    assert secret not in err_str


def test_tavily_search_handles_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=429, json={"detail": "Rate limit exceeded"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TavilySearchAdapter(api_key="tvly_key", client=client)

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        adapter.search("test")

    assert "rate limit" in str(exc_info.value).lower()


def test_tavily_search_handles_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TavilySearchAdapter(api_key="tvly_key", client=client)

    with pytest.raises(LiteBridgeTimeoutError) as exc_info:
        adapter.search("test")

    assert "timed out" in str(exc_info.value).lower()

"""Tavily Basic Search provider adapter for LiteBridge Phase L3."""

from __future__ import annotations

from typing import Any

import httpx

from evidenceops.bridge.errors import (
    LiteBridgeRetrievalError,
    LiteBridgeSourceError,
    LiteBridgeTimeoutError,
)
from evidenceops.bridge.ports import WebSearchHit, WebSearchProvider

TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"


class TavilySearchAdapter(WebSearchProvider):
    """Adapter translating Tavily Basic Search API into LiteBridge WebSearchHit records."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        timeout_ms: int = 5000,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise LiteBridgeSourceError("TAVILY_API_KEY must be a nonblank string")
        self._api_key = api_key.strip()
        self._client = client
        self._timeout_ms = timeout_ms

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        timeout_ms: int | None = None,
    ) -> tuple[WebSearchHit, ...]:
        """Execute Tavily Basic Search and return normalized WebSearchHit tuples."""
        if not isinstance(query, str) or not query.strip():
            from evidenceops.bridge.errors import LiteBridgeValidationError

            raise LiteBridgeValidationError("Search query must be a nonblank string")

        eff_timeout_ms = timeout_ms if timeout_ms is not None else self._timeout_ms
        timeout_seconds = max(eff_timeout_ms / 1000.0, 0.1)
        payload = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            if self._client is not None:
                resp = self._client.post(
                    TAVILY_SEARCH_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=timeout_seconds,
                )
            else:
                with httpx.Client(trust_env=False) as client:
                    resp = client.post(
                        TAVILY_SEARCH_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=timeout_seconds,
                    )
        except httpx.TimeoutException as err:
            raise LiteBridgeTimeoutError("Tavily search request timed out") from err
        except httpx.HTTPError as err:
            raise LiteBridgeRetrievalError(
                f"Tavily search connection error: {type(err).__name__}"
            ) from err
        except Exception as err:
            raise LiteBridgeRetrievalError(
                f"Tavily search unexpected transport error: {type(err).__name__}"
            ) from err

        if resp.status_code in {401, 403}:
            raise LiteBridgeSourceError("Tavily search authentication failed (invalid API key)")
        if resp.status_code == 429:
            raise LiteBridgeRetrievalError("Tavily search rate limit exceeded")
        if resp.status_code != 200:
            raise LiteBridgeRetrievalError(
                f"Tavily search failed with HTTP status {resp.status_code}"
            )

        try:
            data: dict[str, Any] = resp.json()
        except Exception as err:
            raise LiteBridgeRetrievalError("Tavily search returned malformed JSON") from err

        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            return ()

        hits: list[WebSearchHit] = []
        for idx, item in enumerate(raw_results[:max_results]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("content", "")).strip()
            if not url or not snippet:
                continue
            hits.append(
                WebSearchHit(
                    title=title,
                    url=url,
                    snippet=snippet,
                    rank=idx + 1,
                )
            )

        return tuple(hits)

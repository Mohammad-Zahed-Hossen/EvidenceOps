"""SSRF-safe, allowlist-only web page fetcher for LiteBridge Phase L3."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from evidenceops.bridge.errors import (
    LiteBridgeRetrievalError,
    LiteBridgeTimeoutError,
)
from evidenceops.bridge.ports import FetchedWebPage, WebPageFetcher

ALLOWED_CONTENT_TYPES = ("text/html", "text/plain")


class _HTMLTextExtractor(HTMLParser):
    """Safe HTML-to-text extractor stripping scripts, styles, and tags."""

    def __init__(self) -> None:
        super().__init__()
        self._text_chunks: list[str] = []
        self._title_chunks: list[str] = []
        self._in_title = False
        self._ignored_tags = {"script", "style", "noscript", "template", "svg"}
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignored_tags:
            self._ignore_depth += 1
        elif tag_lower == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignored_tags and self._ignore_depth > 0:
            self._ignore_depth -= 1
        elif tag_lower == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignore_depth == 0:
            clean = data.strip()
            if clean:
                if self._in_title:
                    self._title_chunks.append(clean)
                self._text_chunks.append(clean)

    def get_extracted_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._text_chunks)).strip()

    def get_title(self) -> str:
        return " ".join(self._title_chunks).strip()


def _resolve_and_validate_ips(
    hostname: str,
    dns_resolver: Callable[[str], list[str]] | None = None,
) -> list[str]:
    """Resolve hostname and assert that all resolved IP addresses are globally routable."""
    if dns_resolver is not None:
        ip_list = dns_resolver(hostname)
    else:
        try:
            addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
            ip_list = [str(entry[4][0]) for entry in addr_info]
        except socket.gaierror as err:
            raise LiteBridgeRetrievalError(
                f"DNS resolution failed for host '{hostname}': {err}"
            ) from err

    if not ip_list:
        raise LiteBridgeRetrievalError(f"No IP addresses resolved for host '{hostname}'")

    for ip_str in ip_list:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as err:
            raise LiteBridgeRetrievalError(
                f"Invalid IP address '{ip_str}' resolved for host '{hostname}'"
            ) from err

        if (
            ip_obj.is_loopback
            or ip_obj.is_private
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
            or not ip_obj.is_global
        ):
            raise LiteBridgeRetrievalError(
                f"Host '{hostname}' resolved to non-globally-routable address '{ip_str}'"
            )

    return ip_list


def _validate_safe_url(url: str, allowed_domains: tuple[str, ...]) -> tuple[str, str]:
    """Validate URL syntax, HTTPS scheme, credentials, ports, and domain allowlist."""
    if not isinstance(url, str) or not url.strip():
        raise LiteBridgeRetrievalError("URL must be a nonblank string")
    clean_url = url.strip()
    if not clean_url.startswith("https://"):
        raise LiteBridgeRetrievalError(f"Only HTTPS URLs are permitted, got '{clean_url}'")
    parsed = urlparse(clean_url)

    if parsed.username or parsed.password:
        raise LiteBridgeRetrievalError("URL with embedded user credentials is not permitted")
    if parsed.fragment:
        raise LiteBridgeRetrievalError("URL with fragment is not permitted")
    if parsed.port is not None and parsed.port != 443:
        raise LiteBridgeRetrievalError("URL with non-default port is not permitted")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise LiteBridgeRetrievalError("URL has no hostname")

    # Reject IP-literal hostnames
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        raise LiteBridgeRetrievalError(f"IP-literal host '{hostname}' is not permitted")
    except ValueError:
        pass

    if hostname not in allowed_domains:
        raise LiteBridgeRetrievalError(
            f"Host '{hostname}' is not in the configured allowed fetch domains"
        )

    # Canonicalize default port out of netloc
    canonical_url = f"https://{hostname}{parsed.path}"
    if parsed.query:
        canonical_url = f"{canonical_url}?{parsed.query}"

    return canonical_url, hostname


class SafeWebPageFetcher(WebPageFetcher):
    """SSRF-safe page fetcher with domain allowlist, IP validation, and size capping."""

    def __init__(
        self,
        allowed_domains: tuple[str, ...] = (),
        timeout_ms: int = 5000,
        max_response_bytes: int = 200_000,
        max_redirects: int = 3,
        client: httpx.Client | None = None,
        dns_resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        self._allowed_domains = allowed_domains
        self._timeout_ms = timeout_ms
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._client = client
        self._dns_resolver = dns_resolver

    def fetch(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        max_response_bytes: int | None = None,
        allowed_domains: tuple[str, ...] | None = None,
        max_redirects: int | None = None,
    ) -> FetchedWebPage:
        """Fetch and extract safe plaintext from an allowlisted HTTPS page."""
        eff_allowed_domains = (
            allowed_domains if allowed_domains is not None else self._allowed_domains
        )
        eff_timeout_ms = timeout_ms if timeout_ms is not None else self._timeout_ms
        eff_max_bytes = (
            max_response_bytes if max_response_bytes is not None else self._max_response_bytes
        )
        eff_max_redirects = max_redirects if max_redirects is not None else self._max_redirects

        if not eff_allowed_domains:
            raise LiteBridgeRetrievalError(
                "Page fetching is disabled: no domains configured in allowed fetch domains"
            )

        timeout_seconds = max(eff_timeout_ms / 1000.0, 0.1)
        current_url = url
        redirect_count = 0

        while True:
            canonical_url, hostname = _validate_safe_url(current_url, eff_allowed_domains)
            _resolve_and_validate_ips(hostname, self._dns_resolver)

            try:
                if self._client is not None:
                    resp = self._client.get(
                        canonical_url,
                        timeout=timeout_seconds,
                    )
                else:
                    with httpx.Client(trust_env=False, follow_redirects=False) as client:
                        resp = client.get(
                            canonical_url,
                            timeout=timeout_seconds,
                        )
            except httpx.TimeoutException as err:
                raise LiteBridgeTimeoutError(
                    f"Page fetch timed out for URL '{canonical_url}'"
                ) from err
            except httpx.HTTPError as err:
                raise LiteBridgeRetrievalError(
                    f"HTTP error fetching URL '{canonical_url}': {type(err).__name__}"
                ) from err
            except LiteBridgeRetrievalError:
                raise
            except Exception as err:
                raise LiteBridgeRetrievalError(
                    f"Unexpected error fetching URL '{canonical_url}': {type(err).__name__}"
                ) from err

            if resp.status_code in {301, 302, 303, 307, 308}:
                redirect_count += 1
                if redirect_count > eff_max_redirects:
                    raise LiteBridgeRetrievalError(
                        f"Redirect limit exceeded ({eff_max_redirects}) fetching '{url}'"
                    )
                location = resp.headers.get("Location")
                if not location:
                    raise LiteBridgeRetrievalError(
                        f"Redirect response from '{canonical_url}' missing Location header"
                    )
                current_url = urljoin(canonical_url, location)
                continue

            if resp.status_code != 200:
                raise LiteBridgeRetrievalError(
                    f"Page fetch returned non-200 status {resp.status_code} for '{canonical_url}'"
                )

            content_type_header = resp.headers.get("Content-Type", "").lower()
            if not any(
                content_type_header.startswith(allowed_ct) for allowed_ct in ALLOWED_CONTENT_TYPES
            ):
                raise LiteBridgeRetrievalError(
                    f"Unsupported content-type '{content_type_header}' for '{canonical_url}'"
                )

            raw_bytes = resp.content
            if len(raw_bytes) > eff_max_bytes:
                raw_bytes = raw_bytes[:eff_max_bytes]

            charset = resp.encoding or "utf-8"
            try:
                body_text = raw_bytes.decode(charset, errors="replace")
            except Exception:
                body_text = raw_bytes.decode("utf-8", errors="replace")

            extractor = _HTMLTextExtractor()
            extractor.feed(body_text)
            extracted_text = extractor.get_extracted_text()
            page_title = extractor.get_title() or hostname

            content_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
            fetched_at_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            return FetchedWebPage(
                canonical_url=canonical_url,
                title=page_title,
                text=extracted_text,
                content_hash=content_hash,
                fetched_at_utc=fetched_at_utc,
            )

    def fetch_page(self, url: str) -> FetchedWebPage:
        """Convenience method forwarding to fetch."""
        return self.fetch(url)


SafeWebFetcher = SafeWebPageFetcher

__all__ = ["SafeWebFetcher", "SafeWebPageFetcher"]

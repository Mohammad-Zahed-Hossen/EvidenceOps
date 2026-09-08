"""Strict loopback HTTP endpoint validation for LiteBridge local adapters."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from evidenceops.bridge.errors import LiteBridgeValidationError


def validate_loopback_url(raw_url: str, provider_name: str) -> str:
    """Validate and normalize a local loopback HTTP base URL.

    Rules:
        - Scheme must be strictly 'http' (HTTP only, no HTTPS for local daemon).
        - Hostname must be '127.0.0.1', '::1', '[::1]', or 'localhost' resolving
          strictly to loopback.
        - No credentials (username/password) allowed.
        - No query parameters or URL fragments allowed.
        - No non-root paths allowed (e.g. 'http://127.0.0.1:11434/' is normalized to 'http://127.0.0.1:11434').
    """
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise LiteBridgeValidationError(f"{provider_name} base URL must be nonblank")

    trimmed = raw_url.strip()
    try:
        parsed = urlparse(trimmed)
    except Exception as exc:
        raise LiteBridgeValidationError(f"{provider_name} base URL is malformed") from exc

    if parsed.scheme != "http":
        raise LiteBridgeValidationError(
            f"{provider_name} requires http scheme, got '{parsed.scheme}'. "
            "HTTPS and non-HTTP protocols are forbidden for local loopback."
        )

    if parsed.username or parsed.password:
        raise LiteBridgeValidationError(f"{provider_name} forbids embedded URL credentials")

    if parsed.query or parsed.fragment:
        raise LiteBridgeValidationError(
            f"{provider_name} forbids URL query parameters and fragments"
        )

    if parsed.path and parsed.path not in ("", "/"):
        raise LiteBridgeValidationError(
            f"{provider_name} base URL must not contain subpaths, got '{parsed.path}'"
        )

    host = parsed.hostname
    if not host:
        raise LiteBridgeValidationError(f"{provider_name} base URL missing host")

    host_lower = host.lower()
    is_valid_loopback = False

    if host_lower in {"127.0.0.1", "::1"}:
        is_valid_loopback = True
    elif host_lower == "localhost":
        # Verify localhost resolves strictly to loopback
        try:
            addr_info = socket.getaddrinfo("localhost", None, proto=socket.IPPROTO_TCP)
            resolved_ips = {info[4][0] for info in addr_info}
            if resolved_ips and all(ipaddress.ip_address(ip).is_loopback for ip in resolved_ips):
                is_valid_loopback = True
        except Exception:
            is_valid_loopback = False
    else:
        try:
            ip_obj = ipaddress.ip_address(host_lower)
            if ip_obj.is_loopback:
                is_valid_loopback = True
        except ValueError:
            is_valid_loopback = False

    if not is_valid_loopback:
        raise LiteBridgeValidationError(
            f"{provider_name} requires local loopback endpoint "
            f"('127.0.0.1', '[::1]', or 'localhost' resolving to loopback), got '{host}'"
        )

    port_suffix = f":{parsed.port}" if parsed.port else ""
    return f"http://{host}{port_suffix}"

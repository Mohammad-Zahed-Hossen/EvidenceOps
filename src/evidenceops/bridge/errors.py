"""Sanitized, single-inheritance error hierarchy for LiteBridge."""

from __future__ import annotations


class LiteBridgeError(Exception):
    """Base exception for all LiteBridge errors with sanitized public representation."""

    default_code = "litebridge_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class LiteBridgeValidationError(LiteBridgeError):
    """Raised when an input query or caller policy fails validation."""

    default_code = "validation_error"


class LiteBridgeProfileError(LiteBridgeError):
    """Raised when an unsupported execution profile is requested."""

    default_code = "unsupported_profile"


class LiteBridgeRetrievalError(LiteBridgeError):
    """Raised when underlying retrieval fails, without exposing raw backend traces."""

    default_code = "retrieval_error"


class LiteBridgeSourceError(LiteBridgeError):
    """Raised when source registration, lookup, or resolution fails."""

    default_code = "source_error"


class LiteBridgeTimeoutError(LiteBridgeRetrievalError):
    """Raised when retrieval exceeds its deadline or times out."""

    default_code = "timeout_error"


class LiteBridgeProviderError(LiteBridgeError):
    """Raised when an LLM generation provider fails."""

    default_code = "provider_error"


class LiteBridgeProviderUnavailableError(LiteBridgeProviderError):
    """Raised when a generation provider daemon, endpoint, or service is unreachable."""

    default_code = "provider_unavailable"


class LiteBridgeProviderAuthError(LiteBridgeProviderError):
    """Raised when provider authentication fails or credentials are rejected."""

    default_code = "provider_auth_error"


class LiteBridgeProviderRateLimitError(LiteBridgeProviderError):
    """Raised when provider rate limits or quotas are exceeded."""

    default_code = "provider_rate_limit"

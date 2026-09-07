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

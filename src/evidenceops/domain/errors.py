"""Small, framework-independent error hierarchy."""

from collections.abc import Mapping


class EvidenceOpsError(Exception):
    """Base exception with a stable code and non-sensitive string form."""

    default_code = "evidenceops_error"

    def __init__(
        self, message: str, *, code: str | None = None, context: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.context = dict(context or {})

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigurationError(EvidenceOpsError):
    default_code = "configuration_error"


class DomainValidationError(EvidenceOpsError):
    default_code = "domain_validation_error"


class DependencyUnavailableError(EvidenceOpsError):
    default_code = "dependency_unavailable"


class RetrievalError(EvidenceOpsError):
    default_code = "retrieval_error"


class GenerationError(EvidenceOpsError):
    default_code = "generation_error"


class AbstentionError(EvidenceOpsError):
    default_code = "abstention_error"

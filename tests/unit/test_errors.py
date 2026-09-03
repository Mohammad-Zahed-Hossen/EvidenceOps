from evidenceops.domain.errors import ConfigurationError, EvidenceOpsError, RetrievalError


def test_errors_expose_stable_codes_and_safe_strings() -> None:
    error = ConfigurationError("invalid local URL", context={"url": "http://localhost:6333"})
    assert isinstance(error, EvidenceOpsError)
    assert error.code == "configuration_error"
    assert str(error) == "[configuration_error] invalid local URL"
    assert error.context["url"] == "http://localhost:6333"
    assert RetrievalError("not available").code == "retrieval_error"

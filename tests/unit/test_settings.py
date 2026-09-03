import pytest
from pydantic import ValidationError

from evidenceops.settings import Settings, get_settings


def test_settings_have_cpu_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.max_iterations == 3
    assert settings.max_retrieval_calls == 3
    assert settings.embedding_dimension == 384
    assert settings.ollama_model == "qwen2.5:3b-instruct"


def test_settings_allow_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOP_K_CONTEXT", "8")
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "0.2")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.top_k_context == 8
    assert settings.ollama_temperature == 0.2
    get_settings.cache_clear()


@pytest.mark.parametrize("name,value", [("SUFFICIENCY_THRESHOLD", "1.2"), ("MAX_ITERATIONS", "4")])
def test_settings_reject_invalid_guardrails(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

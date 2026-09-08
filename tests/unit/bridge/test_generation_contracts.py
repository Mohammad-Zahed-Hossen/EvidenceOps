"""Unit tests for LiteBridge generation public contracts and derive_answer_id."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.bridge.contracts import (
    GenerationAbstentionReason,
    GenerationPolicy,
    GenerationStatus,
    GenerationUsage,
    GroundedAnswer,
    ProviderCapability,
    ProviderLocation,
    derive_answer_id,
)


def test_generation_policy_defaults_and_bounds() -> None:
    policy = GenerationPolicy()
    assert policy.provider_id is None
    assert policy.temperature == 0.0
    assert policy.max_output_tokens == 512
    assert policy.timeout_ms == 30000
    assert not policy.allow_external_generation
    assert not policy.allow_private_evidence_export

    # Immutable
    with pytest.raises(ValidationError):
        policy.temperature = 0.5  # type: ignore[misc]

    # Extra forbid
    with pytest.raises(ValidationError):
        GenerationPolicy(extra_field="invalid")  # type: ignore[call-arg]

    # Bounds
    with pytest.raises(ValidationError):
        GenerationPolicy(temperature=-0.1)
    with pytest.raises(ValidationError):
        GenerationPolicy(temperature=1.1)
    with pytest.raises(ValidationError):
        GenerationPolicy(max_output_tokens=0)
    with pytest.raises(ValidationError):
        GenerationPolicy(max_output_tokens=2049)
    with pytest.raises(ValidationError):
        GenerationPolicy(timeout_ms=500)
    with pytest.raises(ValidationError):
        GenerationPolicy(timeout_ms=60001)

    # Provider ID pattern
    with pytest.raises(ValidationError):
        GenerationPolicy(provider_id="invalid provider")
    with pytest.raises(ValidationError):
        GenerationPolicy(provider_id="INVALID")
    with pytest.raises(ValidationError):
        GenerationPolicy(provider_id="")


def test_provider_capability_contract() -> None:
    cap = ProviderCapability(
        provider_id="local_ollama",
        display_name="Local Ollama",
        location=ProviderLocation.LOCAL,
        model_id="qwen2.5:1.5b",
        supports_citations=True,
        max_output_tokens=2048,
        enabled=True,
    )
    assert cap.provider_id == "local_ollama"
    assert cap.location == ProviderLocation.LOCAL
    assert cap.enabled is True

    # Extra forbid
    with pytest.raises(ValidationError):
        ProviderCapability(
            provider_id="x",
            display_name="x",
            location=ProviderLocation.LOCAL,
            model_id="m",
            supports_citations=True,
            max_output_tokens=100,
            enabled=True,
            extra="forbidden",  # type: ignore[call-arg]
        )


def test_generation_usage_contract() -> None:
    usage = GenerationUsage()
    assert usage.input_tokens is None
    assert usage.output_tokens is None

    usage_reported = GenerationUsage(input_tokens=10, output_tokens=20)
    assert usage_reported.input_tokens == 10
    assert usage_reported.output_tokens == 20

    with pytest.raises(ValidationError):
        GenerationUsage(input_tokens=-1)


def test_grounded_answer_contract_and_invariants() -> None:
    answer = GroundedAnswer(
        answer_id="ans_test",
        context_package_id="pkg_test",
        provider_id="local_ollama",
        model_id="qwen2.5:1.5b",
        status=GenerationStatus.SUCCESS,
        text="The answer is grounded [C1].",
        cited_evidence_ids=("ev_1",),
        citation_valid=True,
    )
    assert answer.answer_id == "ans_test"
    assert answer.citation_valid is True

    # Invariant: non-SUCCESS status with citation_valid=True must fail
    with pytest.raises(ValidationError, match="citation_valid must be False"):
        GroundedAnswer(
            answer_id="ans_fail",
            context_package_id="pkg_test",
            status=GenerationStatus.ABSTAINED,
            text="Abstained.",
            citation_valid=True,
        )

    # Coercion of lists to tuples
    coerced = GroundedAnswer(
        answer_id="ans_coerced",
        context_package_id="pkg_test",
        status=GenerationStatus.SUCCESS,
        text="Text [C1]",
        cited_evidence_ids=["ev_1"],  # type: ignore[arg-type]
        citation_valid=True,
        warnings=["w1"],  # type: ignore[arg-type]
        timings_ms=[["gen", 12.5]],  # type: ignore[arg-type]
    )
    assert coerced.cited_evidence_ids == ("ev_1",)
    assert coerced.warnings == ("w1",)
    assert coerced.timings_ms == (("gen", 12.5),)


def test_derive_answer_id_determinism() -> None:
    policy = GenerationPolicy(provider_id="local_ollama", temperature=0.0)

    id1 = derive_answer_id(
        context_package_id="pkg_1",
        provider_id="local_ollama",
        model_id="qwen2.5:1.5b",
        policy=policy,
        text="Answer [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_1", "ev_2"),
    )

    # Same inputs (even if cited IDs passed in different order) must match
    id2 = derive_answer_id(
        context_package_id="pkg_1",
        provider_id="local_ollama",
        model_id="qwen2.5:1.5b",
        policy=policy,
        text="Answer [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_2", "ev_1"),
    )
    assert id1 == id2
    assert id1.startswith("ans_")

    # Different text yields different ID
    id3 = derive_answer_id(
        context_package_id="pkg_1",
        provider_id="local_ollama",
        model_id="qwen2.5:1.5b",
        policy=policy,
        text="Different [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_1", "ev_2"),
    )
    assert id1 != id3

    # Different status yields different ID
    id4 = derive_answer_id(
        context_package_id="pkg_1",
        provider_id="local_ollama",
        model_id="qwen2.5:1.5b",
        policy=policy,
        text="Answer [C1]",
        status=GenerationStatus.ABSTAINED,
        cited_evidence_ids=(),
        abstention_reason=GenerationAbstentionReason.NO_EVIDENCE,
    )
    assert id1 != id4

"""Unit tests for grounded prompt builders."""

from __future__ import annotations

from evidenceops.generation.prompts import (
    build_citation_correction_prompt,
    build_direct_answer_prompt,
    build_grounded_prompt,
)


def test_build_grounded_prompt_contains_guardrails_and_untrusted_notice() -> None:
    query = "How to declare a status code in FastAPI?"
    evidence_text = '<evidence id="C1">Use status_code parameter</evidence>'
    messages = build_grounded_prompt(query, evidence_text)
    assert len(messages) == 2
    system_msg = messages[0]["content"]
    user_msg = messages[1]["content"]

    assert "untrusted" in system_msg.lower() or "untrusted" in user_msg.lower()
    assert "[C1]" in system_msg or "citation" in system_msg.lower()
    assert query in user_msg
    assert evidence_text in user_msg


def test_build_direct_answer_prompt_has_no_evidence_blocks() -> None:
    query = "Hello, good morning!"
    messages = build_direct_answer_prompt(query)
    assert len(messages) == 2
    assert "<evidence" not in messages[1]["content"]
    assert query in messages[1]["content"]


def test_build_citation_correction_prompt() -> None:
    query = "How does Qdrant filter?"
    original_answer = "Qdrant filters using payload [C99]."
    errors = ["Unknown citation ID [C99] not present in provided context."]
    evidence_text = '<evidence id="C1">Qdrant filters via must and should</evidence>'

    messages = build_citation_correction_prompt(
        query=query,
        evidence_text=evidence_text,
        previous_answer=original_answer,
        validation_errors=errors,
    )
    assert len(messages) == 2
    user_msg = messages[1]["content"]
    assert "[C99]" in user_msg
    assert "Unknown citation" in user_msg
    assert evidence_text in user_msg

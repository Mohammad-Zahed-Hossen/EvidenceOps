"""Syntactic citation validation for LiteBridge generation responses.

Note on claim discipline:
This module performs syntactic citation validation. It verifies that referenced citation
tokens exist in the ContextPackage and follow exact bracket syntax [C1], [C2], etc.
It does NOT perform semantic claim-level verification or prove that a sentence is
semantically supported by the cited evidence.
"""

from __future__ import annotations

import re

from evidenceops.bridge.contracts import ContextPackage

# Pattern matching any bracket token starting with C or c (citation-like attempt)
CITATION_TOKEN_PATTERN = re.compile(r"\[[cC][^\]]*\]")

# Strict pattern for a valid bracket citation: [C1], [C2], etc. (1-indexed, no leading zeros)
STRICT_CITATION_PATTERN = re.compile(r"^\[C([1-9]\d*)\]$")


def extract_citation_tokens(text: str) -> tuple[str, ...]:
    """Extract all citation-like tokens from text in appearance order."""
    if not text:
        return ()
    return tuple(CITATION_TOKEN_PATTERN.findall(text))


def validate_citations(
    text: str,
    context_package: ContextPackage,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    """Syntactically validate all citation-like tokens against ContextPackage evidence.

    Returns:
        (is_valid, valid_evidence_ids, invalid_tokens)

    Rules:
        - Every citation-like token is checked.
        - Must strictly match ^\\[C[1-9]\\d*\\]$.
        - The referenced index must exist in context_package.evidence.
        - Any malformed, unknown, or out-of-bounds citation causes invalid_tokens to be populated.
        - If any invalid token is present, is_valid is False (fails closed).
        - If the package has evidence, at least one valid citation is required.
        - If the package has no evidence, is_valid is always False.
    """
    tokens = extract_citation_tokens(text)

    # Map citation identifiers (e.g. "C1") to evidence record IDs
    evidence_map: dict[str, str] = {}
    for rec in context_package.evidence:
        clean_cid = rec.citation_id.strip("[]")
        evidence_map[clean_cid] = rec.evidence_id

    valid_evidence_ids: list[str] = []
    invalid_tokens: list[str] = []
    seen_valid_ids: set[str] = set()
    seen_invalid_tokens: set[str] = set()

    for token in tokens:
        match = STRICT_CITATION_PATTERN.match(token)
        if match:
            idx_str = match.group(1)
            cid = f"C{idx_str}"
            if cid in evidence_map:
                ev_id = evidence_map[cid]
                if ev_id not in seen_valid_ids:
                    seen_valid_ids.add(ev_id)
                    valid_evidence_ids.append(ev_id)
            else:
                # Out-of-bounds / unknown citation ID (e.g. [C999])
                if token not in seen_invalid_tokens:
                    seen_invalid_tokens.add(token)
                    invalid_tokens.append(token)
        else:
            # Malformed citation-like token (e.g. [CX], [C1 ], [C0], [c1])
            if token not in seen_invalid_tokens:
                seen_invalid_tokens.add(token)
                invalid_tokens.append(token)

    # Syntactic validity determination
    if invalid_tokens:
        is_valid = False
    elif not context_package.evidence:
        is_valid = False
    elif not valid_evidence_ids:
        is_valid = False
    else:
        is_valid = True

    return is_valid, tuple(valid_evidence_ids), tuple(invalid_tokens)

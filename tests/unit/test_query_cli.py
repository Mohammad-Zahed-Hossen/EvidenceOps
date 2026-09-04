"""Unit tests for the evidenceops-query command line interface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from evidenceops.cli.query import main
from evidenceops.domain.enums import RunStatus
from evidenceops.graph.service import QueryResponse


def test_query_cli_requires_query_argument() -> None:
    code = main([])
    assert code == 2


def test_query_cli_rejects_whitespace_query() -> None:
    code = main(["   "])
    assert code == 2


def test_query_cli_executes_successfully_json_output(capsys: object) -> None:
    mock_resp = QueryResponse(
        run_id="run-cli-test",
        status=RunStatus.COMPLETED,
        answer="FastAPI status codes use status_code [C1].",
        citations=["C1"],
        retrieval_calls=1,
        iterations=0,
        sufficiency_score=0.88,
        conflict_score=0.0,
        duration_ms=50.0,
    )

    with patch("evidenceops.cli.query.QueryService") as mock_service_cls:
        instance = MagicMock()
        instance.execute_query.return_value = mock_resp
        mock_service_cls.return_value = instance

        code = main(["How to declare status code in FastAPI?", "--json"])
        assert code == 0


def test_query_cli_executes_successfully_text_output() -> None:
    mock_resp = QueryResponse(
        run_id="run-cli-test",
        status=RunStatus.COMPLETED,
        answer="FastAPI status codes use status_code [C1].",
        citations=["C1"],
        retrieval_calls=1,
        iterations=0,
        sufficiency_score=0.88,
        conflict_score=0.0,
        duration_ms=50.0,
    )

    with patch("evidenceops.cli.query.QueryService") as mock_service_cls:
        instance = MagicMock()
        instance.execute_query.return_value = mock_resp
        mock_service_cls.return_value = instance

        code = main(["How to declare status code in FastAPI?"])
        assert code == 0


def test_query_cli_handles_abstention() -> None:
    mock_resp = QueryResponse(
        run_id="run-cli-abstain",
        status=RunStatus.ABSTAINED,
        abstention_reason="evidence_below_threshold",
        answer="Unable to answer: evidence below threshold.",
        retrieval_calls=2,
        iterations=2,
        duration_ms=60.0,
    )

    with patch("evidenceops.cli.query.QueryService") as mock_service_cls:
        instance = MagicMock()
        instance.execute_query.return_value = mock_resp
        mock_service_cls.return_value = instance

        code = main(["Unknown out of domain question"])
        assert code == 0

"""Unit tests for the evidenceops-eval CLI interface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from evidenceops.cli.evaluate import main


def test_evaluate_cli_help() -> None:
    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0


def test_evaluate_cli_run_mocked(capsys: object) -> None:
    with (
        patch("evidenceops.cli.evaluate.BenchmarkRunner") as mock_runner_cls,
        patch("evidenceops.cli.evaluate.load_evaluation_dataset") as mock_load,
        patch("evidenceops.evaluation.factory.build_benchmark_systems") as mock_build_systems,
    ):
        mock_build_systems.return_value = []
        mock_load.return_value = []
        runner_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.run_id = "eval_run_1"
        mock_result.system_reports = []
        mock_result.leaderboard_markdown = "# Leaderboard\n"
        runner_instance.run_benchmark.return_value = mock_result
        mock_runner_cls.return_value = runner_instance

        code = main(
            [
                "--dataset",
                "eval/datasets/evidenceops-controlled-v1.json",
                "--split",
                "val",
                "--n-bootstrap",
                "50",
            ]
        )
        assert code == 0

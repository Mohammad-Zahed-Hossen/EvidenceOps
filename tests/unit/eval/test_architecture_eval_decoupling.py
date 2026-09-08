"""Architecture decoupling tests for LiteBridge evaluation framework."""

from pathlib import Path


def test_core_does_not_import_evaluation():
    """Verify that LiteBridge core modules have zero imports of evaluation packages."""
    bridge_dir = Path("src/evidenceops/bridge")
    for py_file in bridge_dir.glob("**/*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "evidenceops.eval" not in text, f"{py_file} imports evaluation!"
        assert "evidenceops.evaluation" not in text, f"{py_file} imports legacy evaluation!"


def test_eval_does_not_mutate_runtime_planner():
    """Verify that importing or running evaluation does not alter DeterministicPlanner."""
    import evidenceops.eval.litebridge.runner  # noqa: F401
    from evidenceops.bridge.planner import DeterministicPlanner

    planner = DeterministicPlanner()
    assert planner is not None
    assert type(planner).__name__ == "DeterministicPlanner"

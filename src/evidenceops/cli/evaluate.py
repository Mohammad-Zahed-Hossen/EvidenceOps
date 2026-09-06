"""Command-line interface for running EvidenceOps evaluation benchmarks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evidenceops.evaluation.contracts import DatasetSplit
from evidenceops.evaluation.dataset import load_evaluation_dataset, split_dataset
from evidenceops.evaluation.runner import BenchmarkRunner


def _eval_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidenceops-eval",
        description="Run reproducible benchmark evaluation across baselines and EvidenceOps.",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="eval/datasets/evidenceops-controlled-v1.json",
        help="Path to evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--split",
        type=str,
        choices=["dev", "val", "test"],
        default="val",
        help="Dataset split to evaluate on (default: val).",
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        default=["all"],
        help="List of systems to evaluate (default: all).",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default="NaiveDenseRAG",
        help="Baseline system name for paired bootstrap comparison (default: NaiveDenseRAG).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="eval/runs",
        help="Directory to save run manifests and leaderboards (default: eval/runs).",
    )
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=500,
        help="Number of bootstrap resamples for significance testing (default: 500).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Optional maximum number of samples to evaluate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _eval_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        sys.stderr.write(f"Dataset file not found: {dataset_path}\n")
        return 2

    target_split = DatasetSplit(args.split)
    all_samples = load_evaluation_dataset(dataset_path)
    splits = split_dataset(all_samples)
    eval_samples = splits[target_split]
    if args.max_samples is not None and args.max_samples > 0:
        eval_samples = eval_samples[: args.max_samples]

    from evidenceops.evaluation.factory import build_benchmark_systems

    runner = BenchmarkRunner(output_dir=Path(args.output_dir))
    systems = build_benchmark_systems(system_names=args.systems)

    result = runner.run_benchmark(
        dataset_id=dataset_path.stem,
        split=target_split,
        samples=eval_samples,
        systems=systems,
        baseline_system_name=args.baseline,
        n_bootstrap_resamples=args.n_bootstrap,
    )

    sys.stdout.write(f"\nBenchmark completed. Run ID: {result.run_id}\n")
    sys.stdout.write(str(result.leaderboard_markdown))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

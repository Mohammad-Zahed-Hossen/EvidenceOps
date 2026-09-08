"""CLI entry point for running LiteBridge L8 evaluation benchmark."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evidenceops.eval.litebridge.runner import LiteBridgeEvaluationRunner


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run LiteBridge reproducible evaluation benchmark",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default="eval/litebridge/manifest.json",
        help="Path to manifest.json (default: eval/litebridge/manifest.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts/litebridge-eval",
        help="Directory to store evaluation reports (default: artifacts/litebridge-eval)",
    )
    parser.add_argument(
        "--timed-passes",
        type=int,
        default=10,
        help="Number of timed execution passes per baseline (default: 10)",
    )

    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        sys.stderr.write(f"Error: Manifest file not found: {manifest_path}\n")
        return 1

    try:
        runner = LiteBridgeEvaluationRunner(
            manifest_path=manifest_path,
            output_dir=args.output_dir,
            timed_passes=args.timed_passes,
        )
        report, report_path = runner.run()
        sys.stdout.write("Evaluation completed successfully!\n")
        sys.stdout.write(f"Dataset: {report.dataset_id}\n")
        sys.stdout.write(f"Manifest SHA-256: {report.manifest_sha256}\n")
        sys.stdout.write(f"Determinism Digest: {report.determinism_digest}\n")
        sys.stdout.write(f"Learned Controller Status: {report.learned_controller_status}\n")
        sys.stdout.write(f"Report saved to: {report_path}\n")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Evaluation run failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""CLI for deterministic local corpus ingestion."""

from __future__ import annotations

import argparse
from pathlib import Path

from evidenceops.domain.enums import IngestionRunStatus
from evidenceops.domain.errors import EvidenceOpsError
from evidenceops.ingestion.pipeline import IngestionRequest, LocalIngestionPipeline
from evidenceops.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a local EvidenceOps corpus")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--overwrite-artifacts", action="store_true")
    args = parser.parse_args(argv)
    root = args.source_root.resolve()
    if not root.is_dir():
        parser.error("--source-root must be an existing directory")
    settings = get_settings()
    extensions = {item.strip().lower() for item in settings.supported_source_extensions.split(",")}
    paths = [
        path
        for path in (root.rglob("*") if args.recursive else root.glob("*"))
        if path.is_file() and path.suffix.lower() in extensions
    ]
    if not paths:
        parser.error("no supported source files found")
    try:
        result = LocalIngestionPipeline(
            root, settings.processed_data_dir, settings.manifest_dir
        ).ingest(IngestionRequest(args.run_id, tuple(paths), args.overwrite_artifacts))
    except EvidenceOpsError as exc:
        print(f"ingestion failed: {exc}")
        return 2
    summary = (
        f"run_id={result.run_id} status={result.manifest.status} "
        f"documents={len(result.document_ids)} chunks={len(result.chunk_ids)} "
        f"created={result.created_artifact_count} "
        f"unchanged={result.unchanged_artifact_count} "
        f"failed={result.failed_source_count} manifest={result.manifest_path}"
    )
    print(summary)
    return (
        0
        if result.manifest.status
        in {IngestionRunStatus.COMPLETED, IngestionRunStatus.COMPLETED_WITH_WARNINGS}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

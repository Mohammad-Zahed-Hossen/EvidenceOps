"""Evaluation job endpoints for EvidenceOps API."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from evidenceops.api.dependencies import get_current_api_service
from evidenceops.api.schemas import (
    ApiEvaluationJobResponse,
    ApiEvaluationRunRequest,
)
from evidenceops.api.service import SYSTEM_NAME_MAP, ApiService
from evidenceops.settings import Settings

logger = logging.getLogger("evidenceops.api.evaluation")

router = APIRouter(tags=["Evaluation"])


def _run_evaluation_worker(
    evaluation_id: str,
    dataset_name: str,
    systems_input: list[str],
    limit: int | None,
    settings: Settings,
    service: ApiService,
) -> None:
    """Background worker thread executing the evaluation benchmark safely."""
    service.update_evaluation_job(
        evaluation_id,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
    )
    try:
        from evidenceops.evaluation.contracts import DatasetSplit
        from evidenceops.evaluation.dataset import load_evaluation_dataset, split_dataset
        from evidenceops.evaluation.factory import build_benchmark_systems
        from evidenceops.evaluation.runner import BenchmarkRunner

        dataset_path = Path("eval/datasets") / f"{dataset_name}.json"
        if not dataset_path.is_file():
            raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

        all_samples = load_evaluation_dataset(dataset_path)
        splits = split_dataset(all_samples)
        eval_samples = splits[DatasetSplit.VAL]
        if limit is not None and limit > 0:
            eval_samples = eval_samples[:limit]

        mapped_systems = [SYSTEM_NAME_MAP.get(s, s) for s in systems_input]
        benchmark_systems = build_benchmark_systems(settings=settings, system_names=mapped_systems)

        runner = BenchmarkRunner(output_dir=settings.api_evaluation_root)
        result = runner.run_benchmark(
            dataset_id=dataset_name,
            split=DatasetSplit.VAL,
            samples=eval_samples,
            systems=benchmark_systems,
            baseline_system_name=mapped_systems[0],
            n_bootstrap_resamples=100,
        )

        relative_ref = f"runs/{result.run_id}/leaderboard.md"
        service.update_evaluation_job(
            evaluation_id,
            status="completed",
            relative_output_reference=relative_ref,
            completed_at=datetime.now(UTC).isoformat(),
        )
    except Exception:
        logger.error("Evaluation job %s failed", evaluation_id)
        service.update_evaluation_job(
            evaluation_id,
            status="failed",
            failure_code="evaluation_failed",
            safe_message="Evaluation benchmark execution failed.",
            completed_at=datetime.now(UTC).isoformat(),
        )


@router.post(
    "/eval/run",
    response_model=ApiEvaluationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_evaluation(
    body: ApiEvaluationRunRequest,
    service: Annotated[ApiService, Depends(get_current_api_service)],
) -> ApiEvaluationJobResponse:
    """Submit a benchmark evaluation job to run asynchronously in the background."""
    if service.has_active_evaluation():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation job already running. System is limited to 1 concurrent evaluation.",
        )

    if not service.work_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Local work already running")

    evaluation_id = f"eval_{uuid.uuid4().hex[:12]}"
    now_str = datetime.now(UTC).isoformat()
    job_resp = ApiEvaluationJobResponse(
        evaluation_id=evaluation_id,
        status="queued",
        dataset_name=body.dataset_name,
        systems=body.systems,
        submitted_at=now_str,
    )
    service.register_evaluation_job(job_resp)

    def execute_worker(*args: object) -> None:
        try:
            _run_evaluation_worker(
                evaluation_id,
                body.dataset_name,
                body.systems,
                body.limit,
                service.settings,
                service,
            )
        finally:
            service.work_lock.release()

    try:
        thread = threading.Thread(
            target=execute_worker,
            args=(
                evaluation_id,
                body.dataset_name,
                body.systems,
                body.limit,
                service.settings,
                service,
            ),
            daemon=True,
        )
        thread.start()
    except Exception:
        service.work_lock.release()
        service.update_evaluation_job(
            evaluation_id,
            "failed",
            failure_code="worker_start_failed",
            safe_message="Evaluation worker unavailable.",
        )
        raise HTTPException(status_code=503, detail="Evaluation worker unavailable") from None

    return job_resp


@router.get("/eval/{evaluation_id}", response_model=ApiEvaluationJobResponse)
async def get_evaluation(
    evaluation_id: str,
    service: Annotated[ApiService, Depends(get_current_api_service)],
) -> ApiEvaluationJobResponse:
    """Poll the status and results of an evaluation job."""
    job = service.get_evaluation_job(evaluation_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation job '{evaluation_id}' not found.",
        )
    return job

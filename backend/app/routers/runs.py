import asyncio
import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.project import Project
from app.models.run import Run, RunPhase
from app.models.user import User
from app.schemas.run import RunCreate, RunRead, RunPhaseRead

router = APIRouter(tags=["runs"])


async def _get_project_or_404(project_id: str, user_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_run_or_404(run_id: str, user_id: str, db: AsyncSession) -> Run:
    result = await db.execute(
        select(Run)
        .join(Project, Run.project_id == Project.id)
        .where(Run.id == run_id, Project.owner_id == user_id)
        .options(selectinload(Run.phases))
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _enqueue_generation(run_id: str, task_id: str) -> None:
    """Send a generation task to the Celery worker (runs via executor — non-blocking)."""
    from app.worker.tasks import run_generation
    run_generation.apply_async(
        args=[run_id],
        task_id=task_id,
        queue="worksheet-generation",
    )


def _revoke_task(task_id: str) -> None:
    """Revoke a Celery task. Removes it from the queue; running tasks are signalled to stop."""
    from app.worker.celery_app import celery_app
    celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    project_id: str,
    body: RunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user.id, db)

    run = Run(
        project_id=project_id,
        status="queued",
        selected_file_ids=body.selected_file_ids,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        parallel_sections=max(1, min(body.parallel_sections or 1, 5)),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Enqueue via executor so Celery's sync call doesn't block the async event loop
    task_id = f"run-{run.id}"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _enqueue_generation, run.id, task_id)

    result = await db.execute(
        select(Run).where(Run.id == run.id).options(selectinload(Run.phases))
    )
    run = result.scalar_one()
    return RunRead.model_validate(run)


@router.get("/runs/{run_id}/phases", response_model=list[RunPhaseRead])
async def get_run_phases(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all phases for a run including their prompt_sent and output (for the log view)."""
    run = await _get_run_or_404(run_id, current_user.id, db)
    return [RunPhaseRead.model_validate(p) for p in run.phases]


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await _get_run_or_404(run_id, current_user.id, db)
    return RunRead.model_validate(run)


async def _get_user_from_token(token: str, db: AsyncSession) -> User:
    from app.auth.jwt import decode_access_token

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/runs/{run_id}/stream")
async def stream_run_progress(
    run_id: str,
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint. Streams Redis pub/sub events for the given run."""
    current_user = await _get_user_from_token(token, db)
    await _get_run_or_404(run_id, current_user.id, db)
    await db.close()  # release connection before long-lived stream

    async def event_generator():
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        channel = f"run:{run_id}:progress"
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)

        try:
            yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"

            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    try:
                        parsed = json.loads(data)
                        if parsed.get("type") in ("run_completed", "run_failed"):
                            break
                    except json.JSONDecodeError:
                        pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await redis_client.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await _get_run_or_404(run_id, current_user.id, db)

    if run.status not in ("queued", "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel run in status '{run.status}'",
        )

    # Revoke the Celery task (removes from queue; signals running task to stop)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _revoke_task, f"run-{run_id}")

    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "cancelled", "run_id": run_id}


@router.post("/runs/{run_id}/phases/{phase_name}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_phase(
    run_id: str,
    phase_name: str,  # kept in URL for API compatibility
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-enqueue the run. The orchestrator skips already-completed phases."""
    run = await _get_run_or_404(run_id, current_user.id, db)

    if run.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only retry failed or cancelled runs",
        )

    run.status = "queued"
    run.error_message = None
    run.started_at = None
    run.completed_at = None

    for phase in run.phases:
        if phase.status in ("failed", "cancelled"):
            phase.status = "queued"
            phase.error_message = None

    await db.commit()

    retry_task_id = f"run-{run_id}-retry-{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _enqueue_generation, run_id, retry_task_id)

    return {"status": "queued", "run_id": run_id}

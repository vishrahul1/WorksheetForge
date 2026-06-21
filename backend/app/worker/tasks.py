import asyncio
import logging
import sys

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """
    Run an async coroutine from a synchronous Celery task.
    Sets WindowsSelectorEventLoopPolicy on Windows to avoid ProactorEventLoop
    issues with psycopg3.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)


@celery_app.task(
    name="app.worker.tasks.run_generation",
    bind=True,
    max_retries=0,
    queue="worksheet-generation",
    time_limit=3600,
    soft_time_limit=3500,
)
def run_generation(self, run_id: str) -> None:
    """Generate a worksheet. Called by the API when a run is created."""
    logger.info("Starting generation for run %s", run_id)
    from app.services.generation.orchestrator import run_generation_pipeline
    _run_async(run_generation_pipeline(run_id))
    logger.info("Generation completed for run %s", run_id)


@celery_app.task(
    name="app.worker.tasks.run_cleanup",
    queue="cleanup",
    time_limit=300,
)
def run_cleanup() -> None:
    """Clean up expired documents and fix stuck runs. Scheduled every 30 min."""
    from app.services.cleanup import run_cleanup_job
    run_cleanup_job()

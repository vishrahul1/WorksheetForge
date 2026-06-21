import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# A run stuck in "running" for longer than this is assumed to have crashed
STUCK_RUN_THRESHOLD_MINUTES = 15


async def cleanup_expired_documents(db: AsyncSession) -> int:
    """
    Delete all documents whose expires_at is in the past.
    Returns the number of documents deleted.
    """
    from app.models.document import Document
    from app.services.storage import delete_document

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Document)
        .where(Document.expires_at < now)
        .options(selectinload(Document.versions))
    )
    expired_docs = result.scalars().all()

    deleted_count = 0
    for doc in expired_docs:
        logger.info("Cleaning up expired document %s (expired %s)", doc.id, doc.expires_at)
        for version in doc.versions:
            try:
                delete_document(version.storage_path)
            except Exception as exc:
                logger.warning("Failed to delete storage object %s: %s", version.storage_path, exc)
        await db.delete(doc)
        deleted_count += 1

    if deleted_count:
        await db.commit()
        logger.info("Cleaned up %d expired documents", deleted_count)

    return deleted_count


async def fix_stuck_runs(db: AsyncSession) -> int:
    """
    Find runs stuck in 'running' status for longer than STUCK_RUN_THRESHOLD_MINUTES.
    These are runs whose worker process crashed mid-generation.
    Marks them as 'failed' so the user can retry.
    Returns the number of runs fixed.
    """
    from app.models.run import Run

    threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_RUN_THRESHOLD_MINUTES)
    result = await db.execute(
        select(Run).where(
            Run.status == "running",
            Run.started_at < threshold,
        )
    )
    stuck_runs = result.scalars().all()

    fixed_count = 0
    for run in stuck_runs:
        logger.warning(
            "Fixing stuck run %s (started %s, threshold %d min)",
            run.id, run.started_at, STUCK_RUN_THRESHOLD_MINUTES,
        )
        run.status = "failed"
        run.error_message = (
            f"Worker process crashed or timed out after {STUCK_RUN_THRESHOLD_MINUTES} minutes. "
            "Retry the run — completed phases will be skipped automatically."
        )
        run.completed_at = datetime.now(timezone.utc)
        fixed_count += 1

    if fixed_count:
        await db.commit()
        logger.info("Fixed %d stuck runs", fixed_count)

    return fixed_count


def run_cleanup_job() -> None:
    """
    Synchronous wrapper for the Celery cleanup task.
    Runs both document expiry cleanup and stuck-run recovery.
    Silently skips if the DB is unreachable.
    """
    import asyncio
    import sys
    from app.database import AsyncSessionLocal

    # psycopg3 requires WindowsSelectorEventLoopPolicy on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def _run():
        try:
            async with AsyncSessionLocal() as session:
                expired = await cleanup_expired_documents(session)
                stuck = await fix_stuck_runs(session)
                logger.info(
                    "Cleanup job done: %d expired docs removed, %d stuck runs fixed",
                    expired, stuck,
                )
        except Exception as exc:
            logger.warning("Cleanup job skipped: %s", exc)

    asyncio.run(_run())

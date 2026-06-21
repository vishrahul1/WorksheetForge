from celery import Celery
from app.config import settings

celery_app = Celery(
    "worksheetforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Use threads instead of fork — works on Windows AND Linux
    worker_pool="threads",
    worker_concurrency=2,

    # Reliability
    task_track_started=True,
    task_acks_late=True,            # ack only after task finishes (safer on crash)
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,            # keep task results for 1 hour

    # Queue routing
    task_default_queue="worksheet-generation",
    task_queues={
        "worksheet-generation": {},
        "cleanup": {},
    },

    # Cleanup runs every 30 minutes via beat
    beat_schedule={
        "cleanup-every-30-minutes": {
            "task": "app.worker.tasks.run_cleanup",
            "schedule": 1800.0,
            "options": {"queue": "cleanup"},
        },
    },
)

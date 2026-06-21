import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chat, documents, files, projects, runs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(
    title="WorksheetForge API",
    description="AI-powered Olympiad/JEE/NEET worksheet generation platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "worksheetforge-api"}


@app.on_event("startup")
async def on_startup():
    """Send a one-time cleanup task on startup via Celery."""
    try:
        from app.worker.tasks import run_cleanup
        run_cleanup.apply_async(
            task_id="cleanup-startup",
            queue="cleanup",
        )
        logging.getLogger(__name__).info("Startup cleanup task sent to Celery")
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not send startup cleanup: %s", exc)

"""FastAPI application entry point for Thought2Do.

Configures the FastAPI app instance, CORS middleware, router
registration for auth/tasks/voice (resilient to routers not yet
implemented), a `/` health endpoint, and an async startup hook that
pings MongoDB. Run via:

    uvicorn app.main:app --reload --port 8000
"""
import importlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.dependencies import database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Thought2Do API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers resiliently: stubs that don't yet define `router`
# are skipped so the app still starts during early build phases.
for _module_path in ("app.routers.auth", "app.routers.tasks", "app.routers.voice"):
    try:
        _module = importlib.import_module(_module_path)
    except ImportError as exc:
        logger.info("Skipping %s (import failed): %s", _module_path, exc)
        continue

    _router = getattr(_module, "router", None)
    if _router is None:
        logger.info("Skipping %s (no `router` attribute yet)", _module_path)
        continue

    app.include_router(_router)
    logger.info("Included router: %s", _module_path)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "message": "Thought2Do API is running"}


@app.on_event("startup")
async def _ping_mongodb_on_startup() -> None:
    try:
        await database.command("ping")
        logger.info("Connected to MongoDB (db=%s)", database.name)
    except Exception as exc:
        logger.error("MongoDB connection failed: %s", exc)
        raise

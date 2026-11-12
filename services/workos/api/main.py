"""Horizon Veridian WorkOS FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_WORKOS_ROOT = str(Path(__file__).resolve().parents[1])
if _WORKOS_ROOT not in sys.path:
    sys.path.insert(0, _WORKOS_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import github, hitl, meeting, slack, threads
from connectors.sprint_loop import poll_slack_and_checkins_once
from core.config import get_settings
from core.store import assert_embedding_dimension_match

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _background_sprint_loop() -> None:
    while True:
        try:
            await poll_slack_and_checkins_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Background sprint poller iteration error: %s", exc)
        await asyncio.sleep(2.5)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    dim = assert_embedding_dimension_match()
    settings = get_settings()
    logger.info(
        "WorkOS API started (env=%s demo=%s evon_model=%s embedding_dim=%d)",
        settings.app_env,
        settings.demo_mode,
        settings.evon_model_name,
        dim,
    )
    poller_task = asyncio.create_task(_background_sprint_loop())
    try:
        yield
    finally:
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Horizon Veridian WorkOS API",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Cache-Control", "X-Accel-Buffering", "Last-Event-ID"],
)

app.include_router(meeting.router, prefix="/api", tags=["Meeting Pipeline"])
app.include_router(hitl.router, prefix="/api", tags=["HITL"])
app.include_router(threads.router, prefix="/api", tags=["SSE & State"])
app.include_router(slack.router, prefix="/api", tags=["Webhooks"])
app.include_router(github.router, prefix="/api", tags=["Webhooks"])


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
async def health() -> dict:
    cfg = get_settings()
    return {
        "status": "healthy",
        "service": "workos",
        "evon_model": cfg.evon_model_name,
        "embedding_dim": cfg.embedding_dim,
        "demo_mode": cfg.demo_mode,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=get_settings().workos_port, reload=True)

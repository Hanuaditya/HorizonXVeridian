"""
api/main.py — Veridian WorkOS FastAPI Application
==================================================
Entry point for the backend server. Registers all routes and middleware.

Start with:
    uvicorn api.main:app --reload --port 8000

Endpoints:
    POST /api/meeting-ended     → triggers Graph A (background task)
    GET  /api/stream/{thread_id}→ SSE stream of graph progress
    POST /api/hitl-resume       → resumes paused Graph A
    POST /api/slack-webhook     → triggers Graph B (Slack path)
    POST /api/github-webhook    → triggers Graph B (GitHub path)
    GET  /api/health            → liveness check
"""

import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.routes import meeting, hitl, slack, github
from api.sse import sse_manager

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Veridian WorkOS API",
    description=(
        "Enterprise AI Chief of Staff — LangGraph backend for meeting-to-action automation. "
        "Graph A: synchronous meeting pipeline. Graph B: async Slack/GitHub tracker."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS Middleware — allow Next.js frontend + any configured origins
# ---------------------------------------------------------------------------

_frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        _frontend_url,
        "http://localhost:3000",   # Next.js dev
        "http://localhost:3001",   # Next.js alt port
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Cache-Control", "X-Accel-Buffering"],
)

# ---------------------------------------------------------------------------
# Route registration — all under /api prefix
# ---------------------------------------------------------------------------

app.include_router(meeting.router, prefix="/api", tags=["Meeting Pipeline"])
app.include_router(hitl.router,    prefix="/api", tags=["HITL"])
app.include_router(slack.router,   prefix="/api", tags=["Webhooks"])
app.include_router(github.router,  prefix="/api", tags=["Webhooks"])


# ---------------------------------------------------------------------------
# SSE Streaming endpoint — registered directly on app (not via router)
# to use StreamingResponse cleanly
# ---------------------------------------------------------------------------

@app.get(
    "/api/stream/{thread_id}",
    tags=["SSE"],
    summary="Stream Graph A progress via Server-Sent Events",
    description=(
        "Open this endpoint from the Next.js frontend after receiving a thread_id "
        "from POST /api/meeting-ended. Streams graph state updates in real-time. "
        "Connection closes when the graph completes or errors."
    ),
)
async def stream_graph_events(thread_id: str) -> StreamingResponse:
    """
    GET /api/stream/{thread_id}

    Returns a Server-Sent Events stream for the given graph thread.
    The frontend opens this immediately after POST /api/meeting-ended.

    Event types streamed:
        processing_started  — graph has started
        task_extracted      — extractor_node completed
        firewall_update     — a checker node flagged a task
        resolution_ready    — resolution_generator_node completed
        hitl_ready          — graph paused, awaiting human review
        hitl_resuming       — manager approved, graph resuming
        dispatched          — tickets created, Slack DMs sent
        complete            — stream closing cleanly
        error               — unhandled exception in graph
    """
    logger.info("GET /api/stream/%s — SSE connection opened.", thread_id)

    return StreamingResponse(
        sse_manager.stream_events(thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["Health"], summary="Liveness check")
async def health_check() -> dict:
    """Returns 200 OK with service status and version."""
    return {
        "status": "healthy",
        "service": "veridian-workos-api",
        "version": "1.0.0",
        "graphs": {
            "graph_a": "loaded",
            "graph_b": "loaded",
        },
    }


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    logger.info("=" * 60)
    logger.info("Veridian WorkOS API starting up.")
    logger.info("  Frontend URL : %s", _frontend_url)
    logger.info("  Docs         : http://localhost:8000/api/docs")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Veridian WorkOS API shutting down.")

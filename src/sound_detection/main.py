"""FastAPI application for sound-detection."""

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from rich.console import Console

from sound_detection.api.v1.routers import (
    biome,
    birdnet_compat,
    debug,
    detections,
    knowledge,
    microphones,
    recordings,
    sites,
    species,
)
from sound_detection.core.config import settings
from sound_detection.utils.audio_io import configure_temp_root

load_dotenv()
logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))
log = structlog.get_logger()
console = Console()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown events."""
    tmp = configure_temp_root()
    console.print(f"[bold green]🚀 Starting {settings.service_name}[/]  tmp={tmp}")
    yield
    console.print("[bold red]⏹️  sound-detection shutting down[/]")


app = FastAPI(
    title="sound-detection",
    description="Bioacoustics ML pipeline for wildlife detection (bats, birds, insects)",
    version="0.2.0",
    lifespan=lifespan,
)

# Birdsong runs on its own origin and fetches these endpoints from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def read_only(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """READ_ONLY=1 rejects anything but GET. Used on the shared box."""
    if os.getenv("READ_ONLY") == "1" and request.method != "GET":
        return JSONResponse({"detail": "read only"}, status_code=403)
    return await call_next(request)


app.include_router(biome.router)
app.include_router(debug.router)
app.include_router(detections.router)
app.include_router(knowledge.router)
app.include_router(microphones.router)
app.include_router(recordings.router)
app.include_router(sites.router)
app.include_router(species.router)
app.include_router(birdnet_compat.router)


@app.get("/health")
async def health_check() -> dict:
    """Simple health check endpoint."""
    return {"status": "healthy", "service": settings.service_name}

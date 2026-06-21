"""FastAPI application for sound-detection."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from rich.console import Console

from sound_detection.api.v1.routers import biome, debug, detections, knowledge, microphones, recordings, sites, species
from sound_detection.core.config import settings

load_dotenv()
logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))
log = structlog.get_logger()
console = Console()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown events."""
    console.print(f"[bold green]🚀 {settings.service_name} starting[/]")
    yield
    console.print("[bold red]⏹️  sound-detection shutting down[/]")


app = FastAPI(
    title="sound-detection",
    description="Bioacoustics ML pipeline for wildlife detection (bats, birds, insects)",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(biome.router)
app.include_router(debug.router)
app.include_router(detections.router)
app.include_router(knowledge.router)
app.include_router(microphones.router)
app.include_router(recordings.router)
app.include_router(sites.router)
app.include_router(species.router)


@app.get("/health")
async def health_check() -> dict:
    """Simple health check endpoint."""
    return {"status": "healthy", "service": settings.service_name}

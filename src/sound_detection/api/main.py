"""FastAPI application for sound-detection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from rich.console import Console

from sound_detection.api.routers import detections
from sound_detection.core.config import settings
from sound_detection.db.session import init_db

log = structlog.get_logger()
console = Console()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown events."""
    console.print(f"[bold green]🚀 {settings.service_name} starting[/]")
    init_db()
    yield
    console.print("[bold red]⏹️  sound-detection shutting down[/]")


app = FastAPI(
    title="sound-detection",
    description="Bioacoustics ML pipeline for wildlife detection (bats, birds, insects)",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(detections.router)


@app.get("/health")
async def health_check() -> dict:
    """Simple health check endpoint."""
    return {"status": "healthy", "service": settings.service_name}


@app.get("/biome/summary")
async def biome_summary(short: bool = True) -> dict:
    """Placeholder for biome status summary (Ollama-enhanced later)."""
    return {
        "summary": "Yard biome is active — 3 bird species and 1 bat detected in last 24h (placeholder)",
        "short": short,
        "last_updated": "just now",
    }

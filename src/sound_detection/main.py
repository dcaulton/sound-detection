"""FastAPI application for sound-detection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from rich.console import Console

from sound_detection.api.v1.routers import debug, detections, microphones, recordings, sites, species
from sound_detection.core.config import settings

load_dotenv()
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

app.include_router(debug.router)
app.include_router(detections.router)
app.include_router(microphones.router)
app.include_router(recordings.router)
app.include_router(sites.router)
app.include_router(species.router)


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

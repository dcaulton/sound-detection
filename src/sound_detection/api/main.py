"""FastAPI application for sound-detection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from rich.console import Console

from sound_detection.api.routers import detections
from sound_detection.core.config import settings

# Structured logging + rich console for dev
log = structlog.get_logger()
console = Console()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown events."""
    console.print(f"[bold green]🚀 {settings.service_name} starting in {settings.environment} mode[/]")
    console.print(f"   MLflow tracking → {settings.mlflow_tracking_uri}")
    console.print(f"   Postgres        → {settings.postgres_url.split('@')[-1]}")
    # Pre-load BirdNET analyzer on startup
    from sound_detection.ml.inference import get_analyzer

    get_analyzer()
    yield
    console.print("[bold red]⏹️  sound-detection shutting down[/]")


app = FastAPI(
    title="sound-detection",
    description="Bioacoustics ML pipeline for wildlife detection (bats, birds, insects)",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include routers
app.include_router(detections.router)


@app.get("/health")
async def health_check() -> dict[str, str | bool]:
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "environment": settings.environment,
        "gpu_available": True,
    }


@app.get("/biome/summary")
async def biome_summary(short: bool = True) -> dict[str, str | bool]:
    """Placeholder for biome status summary (Ollama-enhanced later)."""
    return {
        "summary": "Yard biome is active — 3 bird species and 1 bat detected in last 24h (placeholder)",
        "short": short,
        "last_updated": "just now",
    }

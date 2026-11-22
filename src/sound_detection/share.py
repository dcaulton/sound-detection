"""Lightweight read-only API for Birdsong.

Only the /api/v2 BirdNET-compatible endpoints. No ML, no LLM, no biome export.
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sound_detection.api.v1.routers.birdnet_compat import router as birdnet_router
from sound_detection.core.config import settings

logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("share api starting", service=settings.service_name)
    yield
    log.info("share api shutting down")


app = FastAPI(
    title="sound-detection-share",
    description="Read-only BirdNET-compatible API for Birdsong",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(birdnet_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "sound-detection-share"}

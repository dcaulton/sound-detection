"""Entry point for the sound-detection service."""

import uvicorn

from sound_detection.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "sound_detection.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )

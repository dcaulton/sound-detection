import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sound_detection.core.config import settings

# Get database URL from environment (make dev sets this) or fall back to settings
DATABASE_URL = os.getenv("DATABASE_URL", settings.database_url)

# Normalize to modern psycopg driver if needed
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")

# Async engine only (matching birdseye style)
async_engine = create_async_engine(DATABASE_URL, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

from collections.abc import AsyncGenerator

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, create_engine

from sound_detection.core.config import settings

sync_engine = create_engine(settings.database_url.replace("+aiosqlite", ""), echo=settings.debug)
async_engine = create_async_engine(settings.database_url, echo=settings.debug)

AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def init_db() -> None:
    inspector = inspect(sync_engine)
    if not inspector.get_table_names():
        SQLModel.metadata.create_all(sync_engine)
        print("✅ Database tables created")
    else:
        print("✅ Database already initialized")

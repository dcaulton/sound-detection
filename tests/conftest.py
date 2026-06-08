import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from sound_detection.db.models import SQLModel
from sound_detection.db.session import get_db
from sound_detection.main import app

postgres_container = PostgresContainer(
    image="postgres:16",
    username="postgres",
    password="postgres",
    dbname="sound_detection_test",
)


# These will be initialized inside the setup_test_database fixture
async_engine = None
AsyncTestingSessionLocal = None
TestingSessionLocal = None


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> Generator[None, None, None]:
    postgres_container.start()

    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    db = postgres_container.dbname

    async_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

    os.environ["DATABASE_URL"] = async_url

    global async_engine, AsyncTestingSessionLocal
    async_engine = create_async_engine(async_url, echo=False)
    AsyncTestingSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    db = postgres_container.dbname

    sync_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

    global TestingSessionLocal
    engine = create_engine(sync_url, echo=False)

    SQLModel.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncTestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield
    postgres_container.stop()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> Generator[Any, None, None]:
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncTestingSessionLocal is None:
        raise RuntimeError("AsyncTestingSessionLocal has not been initialized")
    async with AsyncTestingSessionLocal() as session:
        yield session

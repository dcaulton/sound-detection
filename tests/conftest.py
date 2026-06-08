from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from sound_detection.api.main import app
from sound_detection.db.models import SQLModel
from sound_detection.db.session import get_db

postgres_container = PostgresContainer(
    image="postgres:16",
    username="postgres",
    password="postgres",
    dbname="sound_detection_test",
)

TestingSessionLocal = None


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> Generator[None, None, None]:
    postgres_container.start()

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

    def override_get_db() -> Generator[Any, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

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

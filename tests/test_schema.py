from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_database_has_expected_tables(client: TestClient) -> None:
    """Verify core tables exist after migrations run."""
    # Get the engine from the app state (set up in conftest)
    engine: Any = client.app.state.engine  # type: ignore[attr-defined]

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    expected = {"site", "microphone", "recording", "detection"}
    missing = expected - tables

    assert not missing, f"Missing tables in database: {missing}"


@pytest.mark.asyncio
async def test_detection_table_has_v0_2_0_columns(client: TestClient) -> None:
    """Verify new columns from the v0.2.0 migration exist."""
    engine: Any = client.app.state.engine  # type: ignore[attr-defined]
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("detection")}

    expected = {"start_offset", "end_offset", "created_at", "updated_at"}
    missing = expected - columns

    assert not missing, f"Missing columns on detection table: {missing}"


@pytest.mark.asyncio
async def test_site_table_has_timezone(client: TestClient) -> None:
    """Verify the timezone column was added."""
    engine: Any = client.app.state.engine  # type: ignore[attr-defined]
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("site")}

    assert "timezone" in columns, "Missing 'timezone' column on site table"

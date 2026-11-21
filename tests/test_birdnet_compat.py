"""BirdNET-Go compatibility helpers."""

from datetime import UTC, datetime

from sound_detection.api.v1.routers.birdnet_compat import _parse_day, _real_name, _window


def test_parse_day() -> None:
    assert _parse_day(None) is None
    assert _parse_day("2026-07-01") == datetime(2026, 7, 1, tzinfo=UTC)
    assert _parse_day("not-a-date") is None


def test_window_end_is_exclusive() -> None:
    start, end = _window("2026-07-01", "2026-07-30")
    assert start == datetime(2026, 7, 1, tzinfo=UTC)
    assert end == datetime(2026, 7, 31, tzinfo=UTC)


def test_window_all_time() -> None:
    assert _window(None, None) == (None, None)


def test_real_name_rejects_placeholder() -> None:
    assert _real_name("NEEDS COMMON NAME", "Turdus migratorius") is None
    assert _real_name("needs common name", "Turdus migratorius") is None
    assert _real_name("", "Turdus migratorius") is None
    assert _real_name(None, "Turdus migratorius") is None


def test_real_name_keeps_a_real_name() -> None:
    assert _real_name("American Robin", "Turdus migratorius") == "American Robin"


def test_real_name_rejects_echo_of_scientific() -> None:
    assert _real_name("Turdus migratorius", "Turdus migratorius") is None

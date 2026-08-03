from datetime import datetime
from zoneinfo import ZoneInfo


def parse_recording_datetime_from_filename(
    filename: str,
    timezone: str = "UTC",
    min_year: int = 2017,
) -> datetime | None:
    """
    Parses filenames like '20260605_072000T.WAV' into UTC datetime.
    Returns None if year < min_year or parsing fails.
    """
    try:
        base = filename.split(".")[0].replace("T", "")
        dt = datetime.strptime(base, "%Y%m%d_%H%M%S")
    except (ValueError, IndexError):
        return None

    if dt.year < min_year:
        return None

    local_tz = ZoneInfo(timezone)
    recording_datetime = dt.replace(tzinfo=local_tz).astimezone(ZoneInfo("UTC"))
    return recording_datetime

"""Local-day helpers.

Sales are stored in UTC, but a shop owner reads "today" and "this month" in
local time. These helpers give both the UTC query bounds and the offset string
MongoDB needs so `$dateToString` buckets days on the same boundaries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def local_day_start(days_ago: int = 0) -> datetime:
    """Midnight of the local day `days_ago` days back, expressed in UTC."""
    local_now = datetime.now().astimezone()
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return start.astimezone(timezone.utc)


def local_tz_offset() -> str:
    """Current local UTC offset as "+HH:MM", for MongoDB date operators."""
    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def month_bounds(year: int) -> tuple[datetime, datetime]:
    """UTC bounds covering a full local calendar year."""
    local_now = datetime.now().astimezone()
    tzinfo = local_now.tzinfo
    start = datetime(year, 1, 1, tzinfo=tzinfo)
    end = datetime(year + 1, 1, 1, tzinfo=tzinfo)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

"""Locale-independent date helpers for renderers (spec F30, F31).

strftime's abbreviated-month directive follows the process locale, so a
host program that calls setlocale() would change month names in
otherwise identical output. The fixed table pins English. to_utc()
defines one rule for naive datetimes: they mean UTC (matching
core/timeparse.py), while aware values convert properly instead of
being relabeled. Numeric strftime codes (day, year, hour, minute) are
locale-independent and stay in use.
"""

from __future__ import annotations

from datetime import UTC, datetime

MONTH_ABBREV = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def to_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime; naive input is treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def human_date(value: datetime) -> str:
    """Render like 'Apr 25 2026' (zero-padded day, pinned month names)."""
    utc = to_utc(value)
    return f"{MONTH_ABBREV[utc.month - 1]} {utc:%d} {utc.year}"


def human_datetime(value: datetime) -> str:
    """Render like 'Apr 25 2026 · 09:14 UTC' (pinned month names)."""
    utc = to_utc(value)
    return f"{MONTH_ABBREV[utc.month - 1]} {utc:%d} {utc.year} · {utc:%H:%M} UTC"

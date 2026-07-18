"""Shared timestamp parsing (spec F4).

One parser for every metadata timestamp the grader reads. Accepts
ISO-8601 with optional fractional seconds, trailing 'Z', numeric UTC
offsets, space or 'T' separators, and bare dates. Returns UTC-aware
datetimes so downstream formatting never depends on the machine's
timezone; naive input is treated as UTC.

governance.py keeps its own stricter parser until the minor release
(spec F18) — replacing it changes grades.
"""

from __future__ import annotations

from datetime import UTC, datetime


def to_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime; naive input is treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_timestamp(value: str) -> datetime | None:
    """Parse a timestamp string to a UTC-aware datetime, or None."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return to_utc(parsed)

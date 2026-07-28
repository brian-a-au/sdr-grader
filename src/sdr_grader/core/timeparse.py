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

import re
from datetime import UTC, datetime, timedelta, timezone

_ABBREVIATION_SUFFIX = re.compile(
    r"^(?P<local>.+?)\s+(?P<abbreviation>[A-Za-z]{2,5})$"
)
_ABBREVIATION_OFFSETS = {
    "GMT": 0,
    "PDT": -7,
    "PST": -8,
    "UTC": 0,
}


def to_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime; naive input is treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_timestamp(value: str) -> datetime | None:
    """Parse a timestamp string to aware UTC, or None for unknown formats.

    Timezone abbreviations are accepted only from the fixed allowlist above.
    Unknown or ambiguous abbreviations fail deterministically rather than
    consulting the host locale or timezone database.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    abbreviation_match = _ABBREVIATION_SUFFIX.fullmatch(candidate)
    if abbreviation_match is not None:
        abbreviation = abbreviation_match.group("abbreviation").upper()
        offset_hours = _ABBREVIATION_OFFSETS.get(abbreviation)
        if offset_hours is None:
            return None
        try:
            local = datetime.fromisoformat(abbreviation_match.group("local"))
        except ValueError:
            return None
        if local.tzinfo is not None:
            return None
        return local.replace(
            tzinfo=timezone(timedelta(hours=offset_hours))
        ).astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return to_utc(parsed)

"""Shared timestamp parsing (spec F4).

Shared ISO parsing with separate rule and snapshot abbreviation allowlists. Accepts
ISO-8601 with optional fractional seconds, trailing 'Z', numeric UTC
offsets, space or 'T' separators, and bare dates. Returns UTC-aware
datetimes so downstream formatting never depends on the machine's
timezone; naive input is treated as UTC.
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

# Exporter metadata uses the host's timezone abbreviation. Keep reporting's
# extra fixed offsets separate from rule-date parsing, so this presentation
# fix does not change custom governance assessments. Ambiguous abbreviations
# such as CST, IST, and BST need an explicit numeric offset instead.
_SNAPSHOT_ABBREVIATION_OFFSETS = {
    **_ABBREVIATION_OFFSETS,
    "CET": 1, "CEST": 2, "EET": 2, "EEST": 3,
    "EST": -5, "EDT": -4, "MST": -7, "MDT": -6,
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
    return _parse_timestamp(value, _ABBREVIATION_OFFSETS)


def parse_snapshot_timestamp(value: str | None) -> datetime | None:
    """Resolve an exporter timestamp using explicit, host-independent offsets."""
    return _parse_timestamp(value, _SNAPSHOT_ABBREVIATION_OFFSETS)


def select_snapshot_timestamp(*values: object) -> str | None:
    """Prefer the first usable alias; retain unrecognized text if none parses."""
    candidates = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    for candidate in candidates:
        if parse_snapshot_timestamp(candidate) is not None:
            return candidate
    return candidates[0] if candidates else None


def _parse_timestamp(value: str | None, offsets: dict[str, int]) -> datetime | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    abbreviation_match = _ABBREVIATION_SUFFIX.fullmatch(candidate)
    if abbreviation_match is not None:
        abbreviation = abbreviation_match.group("abbreviation").upper()
        offset_hours = offsets.get(abbreviation)
        if offset_hours is None:
            return None
        try:
            local = datetime.fromisoformat(abbreviation_match.group("local"))
            if local.tzinfo is not None:
                return None
            return local.replace(
                tzinfo=timezone(timedelta(hours=offset_hours))
            ).astimezone(UTC)
        except (ValueError, OverflowError):
            return None
    try:
        parsed = datetime.fromisoformat(candidate)
        return to_utc(parsed)
    except (ValueError, OverflowError):
        return None

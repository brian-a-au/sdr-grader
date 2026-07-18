"""Locale-independent date helpers for renderers (spec F30, F31).

strftime's abbreviated-month directive follows the process locale, so a
host program that calls setlocale() would change month names in
otherwise identical output. The fixed table pins English. The shared
core.timeparse.to_utc function defines one rule for naive datetimes:
they mean UTC, while aware values convert properly instead of being
relabeled. Numeric strftime codes (day, year, hour, minute) are locale-
independent and stay in use.
"""

from __future__ import annotations

from datetime import datetime

from sdr_grader.core.timeparse import to_utc

MONTH_ABBREV = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

def human_date(value: datetime) -> str:
    """Render like 'Apr 25 2026' (zero-padded day, pinned month names)."""
    utc = to_utc(value)
    return f"{MONTH_ABBREV[utc.month - 1]} {utc:%d} {utc.year}"


def human_datetime(value: datetime) -> str:
    """Render like 'Apr 25 2026 · 09:14 UTC' (pinned month names)."""
    utc = to_utc(value)
    return f"{MONTH_ABBREV[utc.month - 1]} {utc:%d} {utc.year} · {utc:%H:%M} UTC"

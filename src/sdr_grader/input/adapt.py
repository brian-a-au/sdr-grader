"""Shared platform detection and adapter dispatch."""

from __future__ import annotations

from typing import Any

from sdr_grader.core.exceptions import UnknownPlatformError
from sdr_grader.core.models import Implementation


def adapt_snapshot(
    snapshot: dict[str, Any],
    *,
    source: str,
    platform_override: str | None,
) -> Implementation:
    """Normalize one parsed snapshot with explicit or detected platform."""
    from sdr_grader.adapters.aa import adapt as adapt_aa
    from sdr_grader.adapters.cja import adapt as adapt_cja
    from sdr_grader.input.detect import detect_platform

    platform = platform_override or detect_platform(snapshot)
    if platform == "cja":
        return adapt_cja(snapshot, source=source)
    if platform == "aa":
        return adapt_aa(snapshot, source=source)
    raise UnknownPlatformError(
        f"unknown platform {platform!r}; expected 'cja' or 'aa'"
    )

"""Semantic boolean evidence shared by input-consuming rule boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError, SdrGraderError


def parse_boolean(
    value: Any, *, path: str, error: type[SdrGraderError] = InvalidSnapshotError
) -> bool | None:
    """Null is unavailable; false is evidence. Never include input values in errors."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "false"}:
            return text == "true"
    raise error(f"{path}: expected boolean or true/false string (or null)")


def boolean_aliases(
    source: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    path: str,
    error: type[SdrGraderError] = InvalidSnapshotError,
) -> bool | None:
    """Validate agreeing non-null aliases in one precedence-selected source."""
    selected = None
    for key in keys:
        value = parse_boolean(source.get(key), path=f"{path}.{key}", error=error)
        if value is None:
            continue
        if selected is not None and value != selected:
            raise error(f"{path}.{key}: conflicting boolean aliases")
        selected = value
    return selected

"""Object construction for external JSON used as grading evidence."""

from __future__ import annotations

from typing import Any


class DuplicateJSONKeyError(ValueError):
    """A serialized object repeats a decoded member name."""


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate names without exposing input keys or values in errors."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError("JSON contains duplicate object keys")
        result[key] = value
    return result

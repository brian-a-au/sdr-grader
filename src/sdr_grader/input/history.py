"""Same-instance snapshot-history evidence for directory and trend modes."""

from __future__ import annotations

from pathlib import Path

from sdr_grader.core.exceptions import (
    InvalidSnapshotError,
    UnknownPlatformError,
)
from sdr_grader.core.models import Implementation
from sdr_grader.input.adapt import adapt_snapshot
from sdr_grader.input.loader import _load_from_file


def same_history_identity(
    left: Implementation,
    right: Implementation,
) -> bool:
    """Return whether two snapshots belong to one comparable history."""
    return (
        left.platform == right.platform
        and left.instance_id == right.instance_id
    )


def matching_snapshot_sibling_exists(
    directory: Path,
    *,
    selected_source: Path,
    selected: Implementation,
    platform_override: str | None = None,
) -> bool:
    """Find independent history evidence without trusting snapshot metadata.

    Unreadable, malformed, and unrelated siblings are ignored. They must not
    make a valid selected snapshot fail merely because history is optional.
    """
    selected_path = selected_source.resolve()
    for candidate in sorted(Path(directory).glob("*.json")):
        try:
            if candidate.resolve() == selected_path:
                continue
            sibling = _adapt_file(candidate, platform_override=platform_override)
        except (
            AttributeError,
            InvalidSnapshotError,
            KeyError,
            OSError,
            TypeError,
            UnknownPlatformError,
            ValueError,
        ):
            continue
        if same_history_identity(selected, sibling):
            return True
    return False


def _adapt_file(
    path: Path,
    *,
    platform_override: str | None,
) -> Implementation:
    snapshot, source = _load_from_file(path)
    return adapt_snapshot(
        snapshot,
        source=source,
        platform_override=platform_override,
    )

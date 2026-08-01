"""Grade a directory of snapshots in chronological order.

Each snapshot is loaded, adapted, graded against the rubric, and rolled
up into a TrendReport. The renderer in trend/renderer.py turns that into
HTML; the JSON serializer can write it to disk for downstream tooling.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.grader import grade
from sdr_grader.core.models import Implementation
from sdr_grader.input.adapt import adapt_snapshot
from sdr_grader.input.history import same_history_identity
from sdr_grader.input.loader import (
    _extract_timestamp,
    _load_from_file,
    list_snapshot_candidates,
)
from sdr_grader.rules.rubric import Rubric
from sdr_grader.rules.suppression import Suppression
from sdr_grader.trend.models import TrendPoint, TrendReport


def build_trend_report(
    directory: Path,
    rubric: Rubric,
    *,
    suppression: Suppression | None = None,
    platform_override: str | None = None,
) -> TrendReport:
    """Walk a snapshot directory and produce a chronological TrendReport.

    Snapshots without a parseable filename timestamp are skipped (the trend
    needs a stable ordering). Mixing snapshots from different instances or
    different platforms in the same directory raises InvalidSnapshotError.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise InvalidSnapshotError(f"trend input must be a directory: {directory}")

    candidates = list_snapshot_candidates(directory)
    if not candidates:
        raise InvalidSnapshotError(f"no .json snapshots found in {directory}")

    timestamped_candidates: list[tuple[datetime, Path]] = []
    for path in candidates:
        timestamp = _extract_timestamp(path)
        if timestamp is not None:
            timestamped_candidates.append((timestamp, path))
    if not timestamped_candidates:
        raise InvalidSnapshotError(
            f"no snapshots in {directory} have parseable filename timestamps; "
            "trend reports require timestamped filenames "
            "(e.g. snapshot_2026-04-25.json)."
        )

    points: list[TrendPoint] = []
    first_impl: Implementation | None = None
    instance_id: str | None = None
    instance_name: str | None = None
    platform: str | None = None
    history_present = len(timestamped_candidates) > 1

    for timestamp, path in timestamped_candidates:
        snapshot, source = _load_from_file(path)
        impl = adapt_snapshot(
            snapshot,
            source=source,
            platform_override=platform_override,
        )
        if first_impl is None:
            first_impl = impl
            instance_id = impl.instance_id
            instance_name = impl.instance_name
            platform = impl.platform
        else:
            if impl.platform != platform:
                raise InvalidSnapshotError(
                    f"snapshots in {directory} mix platforms "
                    f"({platform!r} and {impl.platform!r}); trend reports are "
                    "per-platform."
                )
            if not same_history_identity(first_impl, impl):
                raise InvalidSnapshotError(
                    f"snapshots in {directory} cover multiple instance IDs "
                    f"({instance_id!r} and {impl.instance_id!r}); trend reports "
                    "are per-instance."
                )
        impl.history_present = history_present
        report = grade(impl, rubric, suppression=suppression)
        points.append(
            TrendPoint(timestamp=timestamp, source=str(path), report=report)
        )

    points.sort(key=lambda p: p.timestamp)
    assert instance_id is not None and instance_name is not None and platform is not None
    return TrendReport(
        instance_id=instance_id,
        instance_name=instance_name,
        platform=platform,
        pack=rubric.pack,
        pack_version=rubric.version,
        points=points,
    )

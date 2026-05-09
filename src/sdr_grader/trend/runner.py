"""Grade a directory of snapshots in chronological order.

Each snapshot is loaded, adapted, graded against the rubric, and rolled
up into a TrendReport. The renderer in trend/renderer.py turns that into
HTML; the JSON serializer can write it to disk for downstream tooling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt as adapt_cja
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.grader import grade
from sdr_grader.input.detect import detect_platform
from sdr_grader.input.loader import _extract_timestamp
from sdr_grader.render import Report
from sdr_grader.rules.rubric import Rubric
from sdr_grader.rules.suppression import Suppression


@dataclass(frozen=True)
class TrendPoint:
    """One graded snapshot in a chronological series."""

    timestamp: datetime
    source: str           # filesystem path or label
    report: Report        # full single-snapshot Report


@dataclass(frozen=True)
class TrendReport:
    """A series of graded snapshots for a single instance."""

    instance_id: str
    instance_name: str
    platform: str
    pack: str
    pack_version: str
    points: list[TrendPoint] = field(default_factory=list)

    @property
    def first(self) -> TrendPoint:
        return self.points[0]

    @property
    def latest(self) -> TrendPoint:
        return self.points[-1]


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

    candidates = sorted(directory.glob("*.json"))
    if not candidates:
        raise InvalidSnapshotError(f"no .json snapshots found in {directory}")

    points: list[TrendPoint] = []
    instance_id: str | None = None
    instance_name: str | None = None
    platform: str | None = None

    for path in candidates:
        ts = _extract_timestamp(path)
        if ts is None:
            # Trends require a stable ordering; skip files we can't date.
            continue
        snapshot = _read_json(path)
        impl_platform = platform_override or detect_platform(snapshot)
        impl = (adapt_cja if impl_platform == "cja" else adapt_aa)(
            snapshot, source=str(path)
        )
        if instance_id is None:
            instance_id = impl.instance_id
            instance_name = impl.instance_name
            platform = impl.platform
        else:
            if impl.instance_id != instance_id:
                raise InvalidSnapshotError(
                    f"snapshots in {directory} cover multiple instance IDs "
                    f"({instance_id!r} and {impl.instance_id!r}); trend reports "
                    "are per-instance."
                )
            if impl.platform != platform:
                raise InvalidSnapshotError(
                    f"snapshots in {directory} mix platforms "
                    f"({platform!r} and {impl.platform!r}); trend reports are "
                    "per-platform."
                )
        report = grade(impl, rubric, suppression=suppression)
        points.append(TrendPoint(timestamp=ts, source=str(path), report=report))

    if not points:
        raise InvalidSnapshotError(
            f"no snapshots in {directory} have parseable filename timestamps; "
            "trend reports require timestamped filenames "
            "(e.g. snapshot_2026-04-25.json)."
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


def _read_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidSnapshotError(f"could not read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidSnapshotError(f"{path}: not valid JSON: {exc}") from exc

"""Trend data model, importable by presentation code.

TrendPoint and TrendReport live here, in a module whose imports stay
neutral (stdlib plus the Report dataclass from render), so the trend
renderer can depend on them without pulling in the grader, the rubric
loader, or the adapters (spec F28). runner.py re-exports both names for
backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sdr_grader.render import Report


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

    def _require_points(self) -> list[TrendPoint]:
        if not self.points:
            raise ValueError(
                "TrendReport has no points; a trend needs at least one graded snapshot"
            )
        return self.points

    @property
    def first(self) -> TrendPoint:
        return self._require_points()[0]

    @property
    def latest(self) -> TrendPoint:
        return self._require_points()[-1]

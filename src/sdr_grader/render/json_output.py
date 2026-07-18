"""Machine-readable JSON serialization of a Report.

Used by `sdr-grader --json PATH` so CI gates and dashboards can consume the
same data the HTML report displays. The shape is deliberately close to
what dataclasses.asdict would produce, with two adjustments:

- Datetimes are normalized to ISO-8601 in UTC.
- Findings include their full body blocks so consumers can re-render or
  extract item lists.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from sdr_grader.render.dates import to_utc
from sdr_grader.render.renderer import Report


def report_to_dict(report: Report) -> dict[str, Any]:
    """Convert a Report to a JSON-serializable dictionary."""
    data = asdict(report)
    data["generated_at"] = _normalize_datetime(report.generated_at)
    return data


def _normalize_datetime(value: datetime) -> str:
    return to_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")

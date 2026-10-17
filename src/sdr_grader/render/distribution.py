"""Build the renderer's Distribution block from a percentile data file.

The data file is a JSON shape parallel to data/distribution.json bundled
with the package. Replace with real leaderboard data once the opt-in
submission service is built (SPEC §8 deferred items).
"""

from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.render.renderer import (
    Distribution,
    DistributionChart,
    Report,
)
from sdr_grader.render.svg import (
    category_comparison_chart,
    histogram_chart,
)

CATEGORY_DISPLAY = {
    "schema_hygiene": "Schema hygiene",
    "naming_consistency": "Naming",
    "segment_complexity": "Seg. complexity",
    "calc_metric_maint": "Calc. metric maint.",
    "attribution_coverage": "Attribution",
    "governance_posture": "Governance",
}

BUNDLED_PATH = Path(__file__).resolve().parent.parent / "data" / "distribution.json"


def load_distribution_data(path: str | Path | None = None) -> dict[str, Any]:
    """Read a distribution data JSON file (or the bundled default)."""
    p = Path(path) if path else BUNDLED_PATH
    if not p.exists():
        raise InvalidSnapshotError(f"distribution data file not found: {p}")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise InvalidSnapshotError(f"could not read {p}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise InvalidSnapshotError(f"{p}: distribution data is not valid UTF-8") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidSnapshotError(f"{p}: not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise InvalidSnapshotError(f"{p}: distribution data is nested too deeply") from exc
    except ValueError as exc:
        raise InvalidSnapshotError(
            f"{p}: distribution data contains a number that is too large"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidSnapshotError(f"{p}: distribution data must be a JSON object")

    overall = data.get("overall")
    if overall is None:
        overall = {}
    if not isinstance(overall, dict):
        raise InvalidSnapshotError(f"{p}: distribution field overall must be an object")
    categories = data.get("categories")
    if categories is None:
        categories = {}
    if not isinstance(categories, dict):
        raise InvalidSnapshotError(f"{p}: distribution field categories must be an object")

    n_instances = data.get("n_instances")
    if n_instances is not None and (
        isinstance(n_instances, bool) or not isinstance(n_instances, int) or n_instances < 0
    ):
        raise InvalidSnapshotError(
            f"{p}: distribution field n_instances must be a non-negative integer"
        )

    p25 = _require_pct(overall.get("p25", 0), "overall.p25", p)
    p75 = _require_pct(overall.get("p75", 100), "overall.p75", p)
    _require_pct(overall.get("median", 0), "overall.median", p)
    if p25 > p75:
        raise InvalidSnapshotError(
            f"{p}: distribution overall.p25 ({p25}) is greater than overall.p75 ({p75})"
        )
    for slug, category in categories.items():
        if not isinstance(category, dict):
            raise InvalidSnapshotError(
                f"{p}: distribution field categories.{slug} must be an object"
            )
        _require_pct(
            category.get("median", 0),
            f"categories.{slug}.median",
            p,
        )
    return data


def _require_pct(value: Any, field: str, source: Path) -> int | float:
    """Require a finite JSON number inside the inclusive percentage range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSnapshotError(
            f"{source}: distribution field {field} must be a number, got {type(value).__name__}"
        )
    if isinstance(value, float) and not isfinite(value):
        raise InvalidSnapshotError(f"{source}: distribution field {field} must be a finite number")
    if not 0 <= value <= 100:
        raise InvalidSnapshotError(
            f"{source}: distribution field {field} must be between 0 and 100"
        )
    return value


def build_distribution(report: Report, data: dict[str, Any]) -> Distribution:
    """Compose Distribution charts from a Report and percentile data."""
    overall = data.get("overall") or {}
    median = int(overall.get("median", 0))
    p25 = int(overall.get("p25", 0))
    p75 = int(overall.get("p75", 100))
    n = int(data.get("n_instances") or 0)

    overall_chart = DistributionChart(
        label="Overall score vs reference distribution",
        svg=histogram_chart(your_score=report.overall_pct, median=median, p25=p25, p75=p75),
    )

    cat_data = data.get("categories") or {}
    rows: list[tuple[str, int, int]] = []
    for cat in report.categories:
        slug = cat.name.lower().replace(" ", "_")
        median_pct = int((cat_data.get(slug) or {}).get("median", 0))
        rows.append((CATEGORY_DISPLAY.get(slug, cat.name), cat.pct, median_pct))

    cat_label = (
        f"Category scores vs median (n = {n} instances)" if n else "Category scores vs median"
    )
    cat_chart = DistributionChart(
        label=cat_label,
        svg=category_comparison_chart(rows),
    )
    return Distribution(charts=[overall_chart, cat_chart])

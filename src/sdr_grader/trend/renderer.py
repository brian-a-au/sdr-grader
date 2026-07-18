"""Render a TrendReport to a single self-contained HTML file.

Visual register matches the main report (SPEC §3): warm off-white
background, publication-serif body, monospace IDs, severity-colored
accents only. Sparklines are server-side SVG; no JS, no CDN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sdr_grader.trend.models import TrendReport

_HERE = Path(__file__).parent
_RENDER_DIR = _HERE.parent / "render"
_TEMPLATES = _HERE / "templates"
_STATIC = _RENDER_DIR / "static"


@lru_cache(maxsize=1)
def _template():
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env.get_template("trend.html.j2")


@lru_cache(maxsize=1)
def _css() -> str:
    return (_STATIC / "report.css").read_text(encoding="utf-8") + "\n" + _trend_css()


CATEGORY_DISPLAY = {
    "schema_hygiene": "Schema hygiene",
    "naming_consistency": "Naming",
    "segment_complexity": "Seg. complexity",
    "calc_metric_maint": "Calc. metric maint.",
    "attribution_coverage": "Attribution",
    "governance_posture": "Governance",
}


@dataclass(frozen=True)
class _CategoryTrace:
    name: str
    points: list[int]              # one pct value per snapshot
    latest_pct: int
    delta: int                     # latest - first


def render_trend(trend: TrendReport) -> str:
    template = _template()
    css = _css()
    view = _build_view(trend)
    return template.render(trend=view, css=css)


# ---------------------------------------------------------------------------
# View assembly
# ---------------------------------------------------------------------------


def _build_view(trend: TrendReport) -> dict[str, Any]:
    points = trend.points
    pct_series = [p.report.overall_pct for p in points]
    overall_first = pct_series[0]
    overall_latest = pct_series[-1]
    overall_delta = overall_latest - overall_first

    category_traces = _category_traces(trend)
    appeared, disappeared = _findings_churn(trend)

    rows = []
    for p in points:
        rows.append(
            {
                "iso": _format_iso(p),
                "human": _format_human(p),
                "grade": p.report.grade,
                "overall_pct": p.report.overall_pct,
                "finding_count": len(p.report.findings),
                "categories": [
                    {
                        "slug": _category_slug(cat.name),
                        "name": CATEGORY_DISPLAY.get(_category_slug(cat.name), cat.name),
                        "pct": cat.pct,
                        "grade": cat.grade,
                    }
                    for cat in p.report.categories
                ],
            }
        )

    return {
        "instance_id": trend.instance_id,
        "instance_name": trend.instance_name,
        "platform": trend.platform.upper(),
        "pack": trend.pack,
        "pack_version": trend.pack_version,
        "first_iso": _format_iso(points[0]),
        "latest_iso": _format_iso(points[-1]),
        "snapshot_count": len(points),
        "overall_pct_series": pct_series,
        "overall_first": overall_first,
        "overall_latest": overall_latest,
        "overall_delta": overall_delta,
        "overall_latest_grade": trend.latest.report.grade,
        "overall_sparkline": sparkline_svg(pct_series, width=480, height=80),
        "category_traces": [
            {
                "slug": trace.name,
                "display": CATEGORY_DISPLAY.get(trace.name, trace.name),
                "latest_pct": trace.latest_pct,
                "delta": trace.delta,
                "delta_class": _delta_class(trace.delta),
                "sparkline": sparkline_svg(trace.points, width=180, height=44),
            }
            for trace in category_traces
        ],
        "rows": rows,
        "appeared_findings": appeared,
        "disappeared_findings": disappeared,
        "delta_class": _delta_class(overall_delta),
    }


def _category_traces(trend: TrendReport) -> list[_CategoryTrace]:
    """Build one trace per category present across the series.

    Each per-snapshot Report.categories may have a subset of the slug
    inventory (depending on rubric weights), so we union across the series
    and pad missing pcts with the previous known value.
    """
    series_categories: list[list[tuple[str, int]]] = []
    for p in trend.points:
        slugs_pcts = [(_category_slug(c.name), c.pct) for c in p.report.categories]
        series_categories.append(slugs_pcts)

    seen_slugs: list[str] = []
    for slugs in series_categories:
        for slug, _ in slugs:
            if slug not in seen_slugs:
                seen_slugs.append(slug)

    traces: list[_CategoryTrace] = []
    for slug in seen_slugs:
        points: list[int] = []
        for snap in series_categories:
            value = next((pct for s, pct in snap if s == slug), None)
            if value is None and points:
                value = points[-1]
            elif value is None:
                value = 0
            points.append(value)
        traces.append(
            _CategoryTrace(
                name=slug,
                points=points,
                latest_pct=points[-1],
                delta=points[-1] - points[0],
            )
        )
    return traces


def _findings_churn(trend: TrendReport) -> tuple[list[str], list[str]]:
    """Compare first and latest snapshot finding sets.

    appeared = in latest but not in first.
    disappeared = in first but not in latest.
    """
    first = {f.id for f in trend.first.report.findings}
    latest = {f.id for f in trend.latest.report.findings}
    appeared = sorted(latest - first)
    disappeared = sorted(first - latest)
    return appeared, disappeared


# ---------------------------------------------------------------------------
# SVG sparkline
# ---------------------------------------------------------------------------


def sparkline_svg(values: list[int], *, width: int, height: int) -> str:
    """Static SVG line over a 0-100 y-domain, suitable for inline embedding."""
    if not values:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"></svg>'
    pad_x = 8
    pad_y = 8
    inner_w = max(width - pad_x * 2, 1)
    inner_h = max(height - pad_y * 2, 1)
    last_idx = max(len(values) - 1, 1)

    def project(i: int, v: int) -> tuple[float, float]:
        x = pad_x + (i / last_idx) * inner_w
        y = pad_y + (1 - max(0, min(100, v)) / 100) * inner_h
        return x, y

    points = [project(i, v) for i, v in enumerate(values)]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    last_x, last_y = points[-1]
    first_x, first_y = points[0]

    bar_color = "#1a1a1a"
    if values[-1] < 60:
        bar_color = "#8b2a1f"
    elif values[-1] < 70:
        bar_color = "#b8651a"

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="Trend sparkline">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
        f'<line x1="{pad_x}" y1="{height - pad_y}" x2="{width - pad_x}" '
        f'y2="{height - pad_y}" stroke="#d8d6cf"/>'
        f'<polyline fill="none" stroke="{bar_color}" stroke-width="1.6" '
        f'points="{polyline}"/>'
        f'<circle cx="{first_x:.1f}" cy="{first_y:.1f}" r="2" fill="#8a8a82"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="{bar_color}"/>'
        "</svg>"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _category_slug(display_name: str) -> str:
    return display_name.lower().replace(" ", "_")


def _delta_class(delta: int) -> str:
    if delta > 0:
        return "trend-up"
    if delta < 0:
        return "trend-down"
    return "trend-flat"


def _format_iso(point) -> str:
    """ISO date for the trend table."""
    return point.timestamp.replace(tzinfo=None).date().isoformat()


def _format_human(point) -> str:
    return point.timestamp.replace(tzinfo=UTC).strftime("%b %d %Y")


# ---------------------------------------------------------------------------
# Trend-only CSS additions (appended to the main report.css)
# ---------------------------------------------------------------------------


def _trend_css() -> str:
    return """
/* --- trend-specific additions --- */
.trend-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; margin: 24px 0; }
.trend-card { padding: 16px 20px; background: #f3f1ea; border-radius: 6px; }
.trend-card h3 { margin: 0 0 4px 0; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #6b6b66; font-family: 'Söhne', 'Inter', sans-serif; font-weight: 500; }
.trend-card .latest { font-family: 'Charter','Iowan Old Style','Source Serif Pro',Georgia,serif; font-size: 22px; color: #1a1a1a; font-weight: 600; }
.trend-card .delta { font-family: 'Söhne', 'Inter', sans-serif; font-size: 11px; margin-left: 8px; }
.trend-card .delta.trend-up { color: #355c2c; }
.trend-card .delta.trend-down { color: #8b2a1f; }
.trend-card .delta.trend-flat { color: #6b6b66; }
.trend-card svg { width: 100%; height: auto; margin-top: 8px; }
.trend-table { width: 100%; border-collapse: collapse; margin: 16px 0; font-family: 'Söhne', 'Inter', sans-serif; font-size: 13px; }
.trend-table th, .trend-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #ece9e0; }
.trend-table th { color: #6b6b66; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; font-size: 11px; }
.trend-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.trend-table td.grade { font-family: 'Charter','Iowan Old Style','Source Serif Pro',Georgia,serif; font-weight: 600; }
.churn { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 16px 0; }
.churn h3 { font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #6b6b66; font-family: 'Söhne', 'Inter', sans-serif; font-weight: 500; }
.churn ul { padding-left: 20px; margin: 8px 0; }
.churn .empty { color: #8a8a82; font-style: italic; font-size: 13px; }
"""

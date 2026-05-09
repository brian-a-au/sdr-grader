"""Trend reports — grade a directory of snapshots over time (v0.3).

`from sdr_grader.trend import build_trend_report, render_trend` is the
public surface; everything else is internal.
"""

from sdr_grader.trend.renderer import render_trend
from sdr_grader.trend.runner import (
    TrendPoint,
    TrendReport,
    build_trend_report,
)

__all__ = [
    "TrendPoint",
    "TrendReport",
    "build_trend_report",
    "render_trend",
]

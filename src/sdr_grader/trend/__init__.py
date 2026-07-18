"""Trend reports — grade a directory of snapshots over time.

`from sdr_grader.trend import build_trend_report, render_trend` is the
public surface; everything else is internal. build_trend_report loads
lazily because runner.py imports the grader and both adapters; an eager
re-export here would pull the rule engine into every trend import and
defeat the renderer-standalone contract (spec F28).
"""

from __future__ import annotations

from typing import Any

from sdr_grader.trend.models import TrendPoint, TrendReport
from sdr_grader.trend.renderer import render_trend

__all__ = [
    "TrendPoint",
    "TrendReport",
    "build_trend_report",
    "render_trend",
]


def __getattr__(name: str) -> Any:
    if name == "build_trend_report":
        from sdr_grader.trend.runner import build_trend_report

        return build_trend_report
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

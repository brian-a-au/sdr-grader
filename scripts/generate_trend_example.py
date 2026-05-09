"""Generate examples/trend-example.html from a synthetic 4-snapshot series.

Builds a temporary directory of snapshots derived from the messy CJA
fixture, where each snapshot fills in a few more component descriptions,
so the trajectory improves visibly across the four points. Useful as a
reference for what a real cja_auto_sdr snapshot directory + sdr-grader
trend run produces.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXAMPLES = REPO_ROOT / "examples"
STRICT_PACK = REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"


def main() -> int:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    base = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    dates = ["2025-12-01", "2026-01-15", "2026-03-01", "2026-04-25"]
    with TemporaryDirectory() as td_str:
        td = Path(td_str)
        for i, date in enumerate(dates):
            snap = json.loads(json.dumps(base))
            fixes = i * 10
            for j, m in enumerate(snap["metrics"][:38]):
                if j < fixes:
                    m["description"] = "Backfilled description."
            snap["metadata"]["Generation Timestamp"] = f"{date} 09:14:00"
            (td / f"snapshot_{date}.json").write_text(
                json.dumps(snap), encoding="utf-8"
            )

        from sdr_grader.rules.rubric import load_rubric
        from sdr_grader.trend import build_trend_report, render_trend

        trend = build_trend_report(td, load_rubric(STRICT_PACK))
        html = render_trend(trend)
        output = EXAMPLES / "trend-example.html"
        output.write_text(html, encoding="utf-8")
        print(
            f"Wrote {output.relative_to(REPO_ROOT)}: "
            f"{len(trend.points)} snapshots, latest {trend.latest.report.grade} "
            f"({trend.latest.report.overall_pct}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

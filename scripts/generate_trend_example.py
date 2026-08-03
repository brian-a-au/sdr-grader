"""Generate examples/trend-example.html from a synthetic 4-snapshot series.

Builds a temporary directory of synthetic snapshots derived from the messy
CJA fixture. Later snapshots backfill dimension descriptions so the current
strict rubric shows the SCH-003 finding resolve. The result demonstrates the
shape of an sdr-grader trend report without claiming production provenance.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXAMPLES = REPO_ROOT / "examples"
STRICT_PACK = REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"


def generate(output_path: Path):
    """Write the deterministic synthetic trend example and return its model."""
    base = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    dates = ["2025-12-01", "2026-01-15", "2026-03-01", "2026-04-25"]
    with TemporaryDirectory() as td_str:
        td = Path(td_str)
        for i, date in enumerate(dates):
            snap = copy.deepcopy(base)
            fixes = i * 40
            for j, dimension in enumerate(snap["dimensions"][:120]):
                if j < fixes:
                    dimension["description"] = "Backfilled description."
            snap["metadata"]["Generation Timestamp"] = f"{date} 09:14:00"
            (td / f"snapshot_{date}.json").write_text(
                json.dumps(snap), encoding="utf-8"
            )

        from sdr_grader.rules.rubric import load_rubric
        from sdr_grader.trend import build_trend_report, render_trend

        trend = build_trend_report(td, load_rubric(STRICT_PACK))
        html = "\n".join(line.rstrip() for line in render_trend(trend).splitlines()) + "\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    return trend


def main() -> int:
    output = EXAMPLES / "trend-example.html"
    trend = generate(output)
    print(
        f"Wrote {output.relative_to(REPO_ROOT)}: "
        f"{len(trend.points)} snapshots, latest {trend.latest.report.grade} "
        f"({trend.latest.report.overall_pct}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sdr_grader.cli.main import main
from sdr_grader.input.loader import load_snapshot
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend import build_trend_report

rubric = load_rubric("src/sdr_grader/rules/packs/strict")
with TemporaryDirectory(prefix="sdr-offset-") as d:
    folder = Path(d)
    for time, documented in [("2026-04-25T09:00:00+09:00", False), ("2026-04-25T01:00:00Z", True)]:
        snapshot = {
            "metadata": {
                "Data View ID": "dv_x",
                "Generation Timestamp": time,
                "sdr_doc_present": documented,
            },
            "metrics": [],
            "dimensions": [],
        }
        (folder / f"snapshot_{time}.json").write_text(json.dumps(snapshot))
    print("latest selected", Path(load_snapshot(d)[1]).name)
    trend = build_trend_report(folder, rubric)
    for p in trend.points:
        print(p.timestamp, p.report.generated_at, p.report.overall_pct, p.report.grade)
    print("delta", trend.latest.report.overall_pct - trend.first.report.overall_pct)
    print(
        "CLI exit",
        main(
            [
                d,
                "--trend",
                "--fail-below",
                "A",
                "--output",
                "/tmp/audit-offset-trend.html",
                "--quiet",
            ]
        ),
    )

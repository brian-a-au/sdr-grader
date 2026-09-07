import copy
import json
import subprocess
from pathlib import Path

from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt
from sdr_grader.core.grader import grade
from sdr_grader.rules.rubric import load_rubric

ROOT = Path(__file__).resolve().parents[3]
base = {
    "metadata": {"Data View ID": "dv1", "Tool Version": "3.11.7"},
    "metrics": [],
    "dimensions": [],
    "calculated_metrics": {
        "metrics": [
            {
                "id": "cm1",
                "name": "Session count",
                "description": "Counts sessions",
                "metric_references": ["visits"],
                "definition_json": json.dumps(
                    {"func": "calc-metric", "formula": {"func": "metric", "name": "metrics/visits"}}
                ),
            }
        ]
    },
}
for label, refs, canonical in [
    ("healthy-exported", ["visits"], "metrics/visits"),
    ("healthy-canonical", ["metrics/visits"], "metrics/visits"),
    ("broken-full", ["deleted"], "metrics/deleted"),
    ("broken-records", "deleted", "metrics/deleted"),
]:
    s = copy.deepcopy(base)
    record = s["calculated_metrics"]["metrics"][0]
    record["metric_references"] = refs
    record["definition_json"] = json.dumps(
        {"func": "calc-metric", "formula": {"func": "metric", "name": canonical}}
    )
    path = Path("/tmp/adapter-" + label + ".json")
    path.write_text(json.dumps(s))
    output = Path("/tmp/adapter-report-" + label)
    p = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "sdr_grader",
            str(path),
            "--fail-below",
            "C",
            "--quiet",
            "--output",
            str(output.with_suffix(".html")),
            "--json",
            str(output.with_suffix(".json")),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    report = grade(adapt(s), load_rubric(ROOT / "src/sdr_grader/rules/packs/strict"))
    print(
        label,
        report.overall_pct,
        report.grade,
        "exit",
        p.returncode,
        [f.id for f in report.findings],
    )


try:
    adapt_aa(
        {
            "report_suite": {"rsid": "rs1"},
            "metrics": [],
            "dimensions": [],
            "calculated_metrics": [{"id": "cm1", "definition": 7}],
        }
    )
except Exception as e:
    print("malformed-AA:", type(e).__name__, str(e))

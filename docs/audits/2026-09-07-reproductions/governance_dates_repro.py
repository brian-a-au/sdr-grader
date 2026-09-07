from dataclasses import replace
from pathlib import Path

from sdr_grader.adapters.cja import adapt
from sdr_grader.cli.main import _check_threshold
from sdr_grader.core.grader import grade
from sdr_grader.input.loader import _extract_timestamp, _pick_snapshot
from sdr_grader.rules.rubric import RuleDefinition, load_rubric

rubric = load_rubric("src/sdr_grader/rules/packs/strict")
base = {
    "metadata": {"Data View ID": "dv_x", "Generation Timestamp": "2026-01-01T00:00:00Z"},
    "dimensions": [],
    "metrics": [],
}
print("BOOLEAN SIGNALS")
for val in (False, "false", "0", 0, {}, {"present": False}):
    snap = {
        **base,
        "metadata": {**base["metadata"], "history_present": val, "sdr_doc_present": val},
    }
    report = grade(adapt(snap), rubric)
    print(
        repr(val),
        [f.id for f in report.findings],
        report.overall_pct,
        report.grade,
        "--fail-below A exit",
        _check_threshold(report, "A", rubric),
    )
print("GOVERNANCE DATES")
for key, check, params in [
    ("GOV-002", "snapshot_age", {"reference_date": "2026-04-25T00:00:00Z", "max_age_days": 90}),
    ("GOV-006", "doc_drift", {"last_sdr_update_at": "2025-01-01T00:00:00Z", "threshold": 0.2}),
]:
    custom = replace(
        rubric,
        category_weights={"governance_posture": 1.0},
        rules=[RuleDefinition(key, key, "high", ["cja"], check, "governance_posture", params)],
    )
    for timestamp in (
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:00.000Z",
    ):
        snap = {
            **base,
            "metadata": {**base["metadata"], "Generation Timestamp": timestamp},
            "dimensions": [{"id": "d", "name": "Dimension", "modified_at": timestamp}],
        }
        r = grade(adapt(snap), custom)
        print(key, timestamp, [f.id for f in r.findings], r.overall_pct, r.grade)
print("FILENAME OFFSETS")
a = Path("snapshot_2026-04-25T09-00-00+09-00.json")
b = Path("snapshot_2026-04-25T01-00-00Z.json")
for p in [a, b]:
    print(p, _extract_timestamp(p))
print("selected", _pick_snapshot([a, b], at=None))

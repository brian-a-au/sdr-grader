"""Tests for the bundled Claude skill helper (skills/sdr-grader/scripts/query_grade.py).

The helper is shipped as a stand-alone Python script with no third-party
dependencies. It runs against the sdr-grader --json output. These tests
shell out to it the same way the skill does.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "skills" / "sdr-grader" / "scripts" / "query_grade.py"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def grade_json(tmp_path_factory) -> Path:
    """Run sdr-grader against the messy fixture and capture the JSON output."""
    out_dir = tmp_path_factory.mktemp("skill")
    html = out_dir / "out.html"
    js = out_dir / "out.json"
    rc = subprocess.run(
        [
            sys.executable, "-m", "sdr_grader",
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output", str(html),
            "--json", str(js),
            "--quiet",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr
    return js


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_summary_lists_overall_and_categories(grade_json):
    proc = _run(["summary", str(grade_json)])
    assert proc.returncode == 0
    out = proc.stdout
    # Just assert grade letter + some percentage; the exact pct shifts as
    # the rule set evolves.
    assert "F (" in out
    assert "Production Web Analytics" in out
    # Each of the six categories shows up.
    for cat in [
        "schema hygiene", "naming consistency", "segment complexity",
        "calc metric maint", "attribution coverage", "governance posture",
    ]:
        assert cat in out


def test_findings_filter_by_severity(grade_json):
    proc = _run(["findings", str(grade_json), "--severity", "high"])
    assert proc.returncode == 0
    assert "[high" in proc.stdout
    assert "[medium" not in proc.stdout


def test_findings_filter_by_rule_prefix(grade_json):
    proc = _run(["findings", str(grade_json), "--rule", "SEG"])
    assert proc.returncode == 0
    out = proc.stdout
    assert "SEG-002" in out
    assert "SCH-003" not in out


def test_show_prints_body_and_remediation(grade_json):
    proc = _run(["show", str(grade_json), "CALC-014"])
    assert proc.returncode == 0
    out = proc.stdout
    assert "CALC-014" in out
    assert "high" in out
    assert "## How to remediate" in out
    assert "Remediations:" in out


def test_show_unknown_rule_returns_nonzero(grade_json):
    proc = _run(["show", str(grade_json), "DOES-NOT-EXIST"])
    assert proc.returncode == 1


def test_compare_reports_appeared_and_resolved(tmp_path, grade_json):
    """Build a second JSON with one finding suppressed and compare."""
    base = json.loads(grade_json.read_text(encoding="utf-8"))
    other = json.loads(json.dumps(base))
    # Drop one finding from the "other" snapshot; expect it to show as
    # appeared in the comparison.
    dropped = other["findings"].pop(0)
    other_path = tmp_path / "other.json"
    other_path.write_text(json.dumps(other), encoding="utf-8")

    proc = _run(["compare", str(grade_json), str(other_path)])
    assert proc.returncode == 0
    out = proc.stdout
    assert "Appeared since other:" in out
    assert dropped["id"] in out


def test_helper_rejects_missing_file():
    proc = _run(["summary", "/tmp/__sdr_grader_does_not_exist__.json"])
    assert proc.returncode == 1
    assert "file not found" in proc.stderr

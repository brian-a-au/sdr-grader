"""End-to-end CLI tests (Phase 3: Mode 1 only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdr_grader.cli.exit_codes import (
    GRADE_BELOW_THRESHOLD,
    RUBRIC_VALIDATION_FAILURE,
    RUNTIME_ERROR,
    SUCCESS,
)
from sdr_grader.cli.main import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_runs_against_messy_fixture_and_writes_html(tmp_path, capsys):
    output = tmp_path / "report.html"
    rc = main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(output)])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert "SCH-003" in html
    assert "170 components lack descriptions" in html
    assert "Production Web Analytics" in html
    err = capsys.readouterr().err
    # stderr summary mentions the grade letter and the instance.
    assert "grade " in err
    assert "dv_messy_prod_web" in err


def test_cli_default_output_filename_is_keyed_by_instance(tmp_path, monkeypatch, capsys):
    """No --output → default filename must encode the instance so batch runs
    across many instances don't collide on a single grade-{ts}.html name
    (issue #2). report.id is `SDR-{YYYY-MMDD}-{INSTANCE-TOKEN}`."""
    monkeypatch.chdir(tmp_path)
    rc = main([str(FIXTURES / "cja_snapshot_messy.json"), "--quiet"])
    assert rc == SUCCESS
    outputs = list(tmp_path.glob("grade-*.html"))
    assert len(outputs) == 1
    name = outputs[0].name
    # Filename must contain the sanitized instance token so different
    # instances graded at the same second don't write to the same path.
    assert "DV-MESSY-PROD-WEB" in name
    assert name.startswith("grade-SDR-")
    assert name.endswith(".html")


def test_cli_quiet_suppresses_stderr_summary(tmp_path, capsys):
    output = tmp_path / "report.html"
    rc = main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(output), "--quiet"])
    assert rc == SUCCESS
    err = capsys.readouterr().err
    assert err == ""


def test_cli_clean_fixture_grades_well(tmp_path):
    output = tmp_path / "clean.html"
    rc = main([str(FIXTURES / "cja_snapshot_clean.json"), "--output", str(output)])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert "Clean Production Web Analytics" in html
    # The clean fixture has no missing descriptions, so SCH-003 must not fire.
    assert "lack descriptions" not in html


def test_cli_rejects_missing_snapshot(tmp_path, capsys):
    rc = main([str(tmp_path / "does_not_exist.json"), "--output", str(tmp_path / "out.html")])
    assert rc == RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "snapshot file not found" in err


def test_cli_rejects_invalid_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    rc = main([str(bad), "--output", str(tmp_path / "out.html")])
    assert rc == RUNTIME_ERROR
    assert "not valid JSON" in capsys.readouterr().err


def test_cli_rejects_unknown_pack(tmp_path, capsys):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--pack",
            "no_such_pack",
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "not found" in capsys.readouterr().err


def test_cli_rejects_invalid_rubric_dir(tmp_path, capsys):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--rubric",
            str(tmp_path / "no_such_dir"),
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "rubric directory not found" in capsys.readouterr().err


def test_cli_rejects_cja_snapshot_with_aa_override(tmp_path, capsys):
    """A CJA snapshot routed through the AA adapter must fail validation."""
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--platform",
            "aa",
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "report_suite" in capsys.readouterr().err


def test_cli_fail_below_returns_grade_below_threshold(tmp_path):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--quiet",
            "--fail-below",
            "B-",
        ]
    )
    assert rc == GRADE_BELOW_THRESHOLD


def test_cli_fail_below_passes_when_grade_meets_threshold(tmp_path):
    # Clean fixture grades C; D is below it, so the threshold is met.
    # External-context rules (GOV-001/003) fire even on the clean fixture
    # because the loader can't prove history / SDR presence yet.
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--quiet",
            "--fail-below",
            "D",
        ]
    )
    assert rc == SUCCESS


def test_cli_invalid_rubric_yaml_returns_validation_failure(tmp_path, capsys):
    pack = tmp_path / "broken_pack"
    pack.mkdir()
    (pack / "_meta.yaml").write_text("pack: test\n")  # missing required keys
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--rubric",
            str(pack),
        ]
    )
    assert rc == RUBRIC_VALIDATION_FAILURE
    assert "rubric error" in capsys.readouterr().err


def test_cli_json_output_writes_machine_readable_report(tmp_path):
    import json

    output = tmp_path / "out.html"
    json_path = tmp_path / "out.json"
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(output),
            "--json",
            str(json_path),
            "--quiet",
        ]
    )
    assert rc == SUCCESS
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["grade"]
    assert isinstance(data["overall_pct"], int)
    assert isinstance(data["findings"], list)
    assert {"name", "pct", "grade"} <= set(data["categories"][0].keys())
    assert data["generated_at"].endswith("Z")


def test_cli_run_is_deterministic(tmp_path):
    """Running twice on the same input must produce byte-identical output."""
    out_a = tmp_path / "a.html"
    out_b = tmp_path / "b.html"
    main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(out_a), "--quiet"])
    main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(out_b), "--quiet"])
    assert out_a.read_bytes() == out_b.read_bytes()


@pytest.fixture
def _changed_snapshot_path(tmp_path):
    """Copy of the messy snapshot with one description filled in."""
    src = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    # First metric was empty ("-"); document it.
    src["metrics"][0]["description"] = "Documented by test."
    out = tmp_path / "modified.json"
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def test_cli_finding_count_drops_when_descriptions_filled_in(tmp_path, _changed_snapshot_path):
    output = tmp_path / "report.html"
    rc = main([str(_changed_snapshot_path), "--output", str(output), "--quiet"])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    # The finding count is 169 now (one fewer); rule still fires.
    assert "169 components lack descriptions" in html


def _make_trend_dir(tmp_path: Path) -> Path:
    """Two dated copies of the messy fixture = a minimal trend directory."""
    src = (FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8")
    d = tmp_path / "snaps"
    d.mkdir()
    (d / "snapshot_2026-01-01.json").write_text(src, encoding="utf-8")
    (d / "snapshot_2026-02-01.json").write_text(src, encoding="utf-8")
    return d


def test_trend_fail_below_gates_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _make_trend_dir(tmp_path)
    rc = main([str(d), "--trend", "--quiet", "--fail-below", "A"])
    assert rc == GRADE_BELOW_THRESHOLD


def test_trend_rejects_flags_it_cannot_honor(tmp_path, capsys):
    d = _make_trend_dir(tmp_path)
    rc = main([str(d), "--trend", "--json", str(tmp_path / "out.json")])
    assert rc == RUNTIME_ERROR
    assert "--json" in capsys.readouterr().err

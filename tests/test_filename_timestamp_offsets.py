"""Filename chronology preserves complete offset and fractional evidence (R2)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.input.loader import _extract_timestamp, load_snapshot
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend import build_trend_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("token", "expected"), [
    ("2026-04-25T09:00:00+09:00", "2026-04-25T00:00:00Z"),
    ("2026-04-25T01:00:00-03:30", "2026-04-25T04:30:00Z"),
    ("2026-04-25T09_00_00+09_00", "2026-04-25T00:00:00Z"),
    ("2026-04-25T09:00:00+0900", "2026-04-25T00:00:00Z"),
    ("2026-04-25T00:00:00+05:30", "2026-04-24T18:30:00Z"),
    ("2026-04-25T23:00:00-02:00", "2026-04-26T01:00:00Z"),
    ("2026-04-25T09-00-00.125+09-00", "2026-04-25T00:00:00.125Z"),
    ("2026-04-25T09-00-00.125-03-30", "2026-04-25T12:30:00.125Z"),
    ("2026-04-25T09:00:00.999999Z", "2026-04-25T09:00:00.999999Z"),
    ("2026_04_25_09_14_00", "2026-04-25T09:14:00Z"),
    ("2026-04-25-09-14", "2026-04-25T09:14:00Z"),
    ("2026-04-25T09:14", "2026-04-25T09:14:00Z"),
    ("2026-04-25", "2026-04-25T00:00:00Z"),
])
def test_complete_filename_timestamp(token, expected):
    assert _extract_timestamp(Path(f"snapshot_{token}.json")) == datetime.fromisoformat(expected)


@pytest.mark.parametrize("token", [
    "2026-99-25", "2026-02-30", "2026-04-25T25:00:00Z",
    "2026-04-25T09:00:00+24:00", "2026-04-25T09:00:00+09:60",
    "2026-04-25T09:00:00+", "2026-04-25T09:00:00+09:",
    "2026-04-25T09:00:00-09:", "2026-04-25T09:00:00-",
    "2026-04-25T09:00:00-09:60",
    "2026-04-25T09:00:00.", "2026-04-25T", "2026-04-25T09:",
    "2026-04-25T09:00:00Z+09:00", "2026-04-25T09:00:00+oops",
    "2026-04-25T09:00:00Zgarbage", "2026-04-25T09:00:00UTC",
])
def test_malformed_token_is_contextual_error(token, tmp_path):
    path = tmp_path / f"snapshot_{token}.json"
    path.write_text("{}")
    with pytest.raises(InvalidSnapshotError, match="filename timestamp") as exc:
        load_snapshot(str(tmp_path))
    assert str(path) in str(exc.value)
    with pytest.raises(InvalidSnapshotError, match="filename timestamp"):
        build_trend_report(tmp_path, load_rubric(ROOT / "src/sdr_grader/rules/packs/strict"))


def test_offsets_and_fractions_drive_latest_and_cutoffs(tmp_path):
    early = tmp_path / "snapshot_2026-04-25T09:00:00+09:00.json"
    late = tmp_path / "snapshot_2026-04-25T01:00:00.125Z.json"
    early.write_text('{"which":"early"}')
    late.write_text('{"which":"late"}')
    assert load_snapshot(str(tmp_path))[1] == str(late)
    for cutoff in ["2026-04-25T00:00:00Z", "2026-04-25T01:00:00.124Z"]:
        assert load_snapshot(str(tmp_path), at=cutoff)[1] == str(early)
    for cutoff in ["2026-04-25T01:00:00.125Z", "2026-04-26"]:
        assert load_snapshot(str(tmp_path), at=cutoff)[1] == str(late)
    with pytest.raises(InvalidSnapshotError, match="at or before"):
        load_snapshot(str(tmp_path), at="2026-04-24T23:59:59.999999Z")


def test_equivalent_instants_retain_stable_path_ties(tmp_path):
    snapshot = (ROOT / "tests/fixtures/cja_snapshot_clean.json").read_text()
    paths = [tmp_path / f"{prefix}_{token}.json" for prefix, token in [
        ("a", "2026-04-25T09:00:00+09:00"),
        ("b", "2026-04-25T00:00:00Z"),
    ]]
    for path in paths:
        path.write_text(snapshot)
    assert load_snapshot(str(tmp_path))[1] == str(paths[0])
    trend = build_trend_report(tmp_path, load_rubric(ROOT / "src/sdr_grader/rules/packs/strict"))
    assert [p.source for p in trend.points] == [str(p) for p in paths]
    assert trend.points[0].timestamp == trend.points[1].timestamp


def test_timestamp_search_does_not_read_parent_directory(tmp_path):
    assert _extract_timestamp(tmp_path / "2026-04-25" / "latest.json") is None
    assert _extract_timestamp(Path("snapshot_2026-04-25.json")) == datetime(2026, 4, 25, tzinfo=UTC)


@pytest.mark.parametrize("token", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_unrepresentable_filename_instant_is_contextual_input_error(token):
    with pytest.raises(InvalidSnapshotError, match="filename timestamp"):
        _extract_timestamp(Path(f"snapshot_{token}.json"))


def test_offset_chronology_corrects_trend_and_latest_gate(tmp_path):
    for token, documented in [
        ("2026-04-25T09:00:00+09:00", False),
        ("2026-04-25T01:00:00Z", True),
    ]:
        snapshot = {"metadata": {"Data View ID": "dv_x", "Generation Timestamp": token,
                                 "sdr_doc_present": documented},
                    "metrics": [], "dimensions": []}
        (tmp_path / f"snapshot_{token}.json").write_text(json.dumps(snapshot))
    trend = build_trend_report(tmp_path, load_rubric(ROOT / "src/sdr_grader/rules/packs/strict"))
    assert [p.report.overall_pct for p in trend.points] == [89, 100]
    assert trend.points[-1].report.overall_pct - trend.points[0].report.overall_pct == 11
    assert main([str(tmp_path), "--trend", "--fail-below", "A",
                 "--output", str(tmp_path / "trend.html"), "--quiet"]) == 0
    assert "100" in (tmp_path / "trend.html").read_text()
    report_json = tmp_path / "report.json"
    assert main([str(tmp_path), "--fail-below", "A", "--json", str(report_json),
                 "--output", str(tmp_path / "latest.html"), "--quiet"]) == 0
    payload = json.loads(report_json.read_text())
    assert payload["overall_pct"] == 100
    assert payload["grade"] == "A"
    assert payload["schema_version"] == 1
    assert "100" in (tmp_path / "latest.html").read_text()


@pytest.mark.parametrize("trend", [False, True])
def test_malformed_filename_cli_preserves_outputs(tmp_path, capsys, trend):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    bad = snapshots / "snapshot_2026-04-25T09:00:00+09:.json"
    bad.write_text("{}")
    html = tmp_path / "report.html"
    report_json = tmp_path / "report.json"
    html.write_text("prior HTML")
    report_json.write_text("prior JSON")
    args = [str(snapshots), "--output", str(html)]
    args += ["--trend"] if trend else ["--json", str(report_json)]
    assert main(args) == 1
    assert str(bad) in capsys.readouterr().err
    assert html.read_text() == "prior HTML"
    assert report_json.read_text() == "prior JSON"


def test_fractional_seconds_order_snapshots_with_identical_clock(tmp_path):
    for prefix, fraction in [("a", "900"), ("b", "100")]:
        (tmp_path / f"{prefix}_2026-04-25T01:00:00.{fraction}Z.json").write_text("{}")
    assert Path(load_snapshot(str(tmp_path))[1]).name.startswith("a_")
    assert Path(load_snapshot(str(tmp_path), at="2026-04-25T01:00:00.500Z")[1]).name.startswith("b_")


@pytest.mark.parametrize("label", ["_export", "-export"])
@pytest.mark.parametrize("token,hour,minute", [("2026-04-25", 0, 0),
                                               ("2026-04-25T09-14-00", 9, 14)])
def test_filename_label_is_outside_timestamp_token(label, token, hour, minute):
    assert _extract_timestamp(Path(f"export_{token}{label}.json")) == datetime(
        2026, 4, 25, hour, minute, tzinfo=UTC
    )

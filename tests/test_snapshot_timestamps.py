"""Snapshot timestamp evidence must survive aliasing and render truthfully."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt as adapt_cja
from sdr_grader.cli.main import main
from sdr_grader.core.grader import grade
from sdr_grader.core.timeparse import parse_snapshot_timestamp, parse_timestamp
from sdr_grader.render import render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.rubric import load_rubric

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(platform, primary, secondary):
    snapshot = json.loads((ROOT / "tests/fixtures" / f"{platform}_snapshot_clean.json").read_text())
    if platform == "cja":
        for key in ("Generation Timestamp", "generation_timestamp", "generated_at"):
            snapshot["metadata"].pop(key, None)
        snapshot["metadata"]["Generation Timestamp"] = primary
        snapshot["metadata"]["Generated Date & timestamp and timezone"] = secondary
    else:
        snapshot["captured_at"] = primary
        snapshot["captured"] = secondary
    return snapshot


@pytest.mark.parametrize("platform", ["cja", "aa"])
@pytest.mark.parametrize(
    "primary", [None, "", "   ", "not-a-date", 123, {"date": "bad"}, "2026-09-30 14:20:00 CST"]
)
def test_usable_alias_reaches_html_and_json(platform, primary):
    snapshot = _snapshot(platform, primary, "2026-09-30T14:20:00+02:00")
    impl = (adapt_cja if platform == "cja" else adapt_aa)(snapshot)
    report = grade(impl, load_rubric(ROOT / "src/sdr_grader/rules/packs/strict"))
    payload = report_to_dict(report)
    assert payload["generated_at"] == "2026-09-30T12:20:00Z"
    assert payload["generated_at_source"] == "snapshot"
    assert "Sep 30 2026 · 12:20 UTC" in render(report)
    assert "Snapshot captured" in render(report)


@pytest.mark.parametrize(
    "zone,hour",
    [
        ("CET", 13),
        ("CEST", 12),
        ("EET", 12),
        ("EEST", 11),
        ("EST", 19),
        ("EDT", 18),
        ("MST", 21),
        ("MDT", 20),
    ],
)
def test_exporter_offsets_are_resolved_for_reporting_only(zone, hour):
    raw = f"2026-09-30 14:20:00 {zone}"
    assert parse_snapshot_timestamp(raw) == datetime(2026, 9, 30, hour, 20, tzinfo=UTC)
    assert parse_timestamp(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not-a-date",
        "2026-09-30 14:20:00 BST",
        "2026-09-30 14:20:00 IST",
        "2026-09-30 14:20:00 CST",
    ],
)
def test_unavailable_timestamp_is_not_presented_as_a_real_jan_1_date(raw):
    impl = adapt_cja(_snapshot("cja", raw, None))
    rubric = load_rubric(ROOT / "src/sdr_grader/rules/packs/strict")
    report = grade(impl, rubric)
    html = render(report)
    assert "Timestamp unavailable" in html
    assert "timestamp is missing or unrecognized" in html
    assert "Jan 01 2026" not in html
    assert "2026-01-01T00:00:00Z" not in html
    payload = report_to_dict(report)
    assert payload["schema_version"] == 1
    assert payload["generated_at"] == "2026-01-01T00:00:00Z"
    assert payload["generated_at_source"] == "fallback"
    assert render(grade(impl, rubric)) == html


def test_genuine_jan_1_timestamp_remains_available():
    impl = adapt_cja(_snapshot("cja", "2026-01-01T00:00:00Z", "2026-09-30T00:00:00Z"))
    report = grade(impl, load_rubric(ROOT / "src/sdr_grader/rules/packs/strict"))
    assert report.generated_at_source == "snapshot"
    assert "Jan 01 2026 · 00:00 UTC" in render(report)
    assert "Timestamp unavailable" not in render(report)


def test_cja_exporter_timestamp_flows_through_cli_reproducibly(tmp_path):
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(_snapshot("cja", None, "2026-09-30 14:20:00 CEST")))
    html = tmp_path / "grade.html"
    output = tmp_path / "grade.json"
    args = [str(source), "--output", str(html), "--json", str(output), "--quiet"]
    assert main(args) == 0
    first_html, first_json = html.read_bytes(), output.read_bytes()
    assert json.loads(first_json)["generated_at"] == "2026-09-30T12:20:00Z"
    assert "Sep 30 2026 · 12:20 UTC" in first_html.decode()
    assert main(args) == 0
    assert (html.read_bytes(), output.read_bytes()) == (first_html, first_json)

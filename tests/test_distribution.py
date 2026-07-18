"""Tests for distribution context (--distribution-data) and supplementary inputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdr_grader.cli.exit_codes import RUNTIME_ERROR, SUCCESS
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.render.distribution import (
    BUNDLED_PATH,
    build_distribution,
    load_distribution_data,
)
from sdr_grader.render.renderer import (
    Adapter,
    Category,
    Methodology,
    Report,
)
from sdr_grader.render.renderer import (
    Rubric as RenderRubric,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _stub_report(overall_pct: int = 54) -> Report:
    return Report(
        id="SDR-TEST",
        instance_name="Test",
        grade="F",
        overall_pct=overall_pct,
        components_evaluated=100,
        components_skipped=0,
        components_skipped_reason=None,
        adapter=Adapter(platform="CJA", tool="cja_auto_sdr", version="3.5.17"),
        rubric=RenderRubric(pack="strict", version="0.4"),
        generated_at=datetime(2026, 4, 25, 9, 14, tzinfo=UTC),
        tldr_html="...",
        categories=[
            Category("schema hygiene", 55, "F"),
            Category("naming consistency", 100, "A"),
            Category("segment complexity", 50, "F"),
            Category("calc metric maint", 44, "F"),
            Category("attribution coverage", 20, "F"),
            Category("governance posture", 46, "F"),
        ],
        remediations=[],
        findings=[],
        methodology=Methodology(paragraphs=["..."]),
    )


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def test_load_distribution_uses_bundled_default():
    data = load_distribution_data(BUNDLED_PATH)
    assert "overall" in data
    assert "categories" in data


def test_load_distribution_rejects_missing_file(tmp_path):
    with pytest.raises(InvalidSnapshotError, match="not found"):
        load_distribution_data(tmp_path / "nope.json")


def test_load_distribution_rejects_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    with pytest.raises(InvalidSnapshotError, match="not valid JSON"):
        load_distribution_data(bad)


def test_out_of_range_overall_percentile_fails_at_load(tmp_path):
    p = tmp_path / "dist.json"
    p.write_text(
        json.dumps({"overall": {"median": 500, "p25": 10, "p75": 90}}),
        encoding="utf-8",
    )
    with pytest.raises(InvalidSnapshotError, match="overall.median"):
        load_distribution_data(p)


def test_inverted_percentiles_fail_at_load(tmp_path):
    p = tmp_path / "dist.json"
    p.write_text(
        json.dumps({"overall": {"median": 50, "p25": 90, "p75": 10}}),
        encoding="utf-8",
    )
    with pytest.raises(InvalidSnapshotError, match="overall.p25"):
        load_distribution_data(p)


@pytest.mark.parametrize("median", ["50", True, "high", -1, 101])
def test_invalid_category_median_fails_at_load(tmp_path, median):
    """Spec F41: category medians must be JSON numbers in range."""
    p = tmp_path / "dist.json"
    p.write_text(
        json.dumps(
            {
                "overall": {"median": 50, "p25": 10, "p75": 90},
                "categories": {"schema_hygiene": {"median": median}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        InvalidSnapshotError,
        match="categories.schema_hygiene.median",
    ):
        load_distribution_data(p)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"overall": []}, "overall must be an object"),
        ({"categories": []}, "categories must be an object"),
        (
            {"categories": {"schema_hygiene": []}},
            "categories.schema_hygiene must be an object",
        ),
    ],
)
def test_distribution_sections_must_be_objects(tmp_path, payload, message):
    p = tmp_path / "dist.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InvalidSnapshotError, match=message):
        load_distribution_data(p)


def test_build_distribution_includes_overall_and_category_charts():
    data = load_distribution_data(BUNDLED_PATH)
    distribution = build_distribution(_stub_report(), data)
    assert len(distribution.charts) == 2
    assert "Overall" in distribution.charts[0].label
    assert "Category" in distribution.charts[1].label
    # Histogram embeds the snapshot's score and the median from the data.
    assert "you · 54" in distribution.charts[0].svg
    assert "median 67" in distribution.charts[0].svg


def test_cli_attaches_distribution_when_flag_set(tmp_path):
    output = tmp_path / "out.html"
    rc = main([
        str(FIXTURES / "cja_snapshot_messy.json"),
        "--output", str(output),
        "--distribution-data", "bundled",
        "--quiet",
    ])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert "median 67" in html


def test_cli_skips_distribution_without_flag(tmp_path):
    output = tmp_path / "out.html"
    rc = main([
        str(FIXTURES / "cja_snapshot_messy.json"),
        "--output", str(output),
        "--quiet",
    ])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    # The distribution section is gated on report.distribution being non-None.
    assert "median 67" not in html


# ---------------------------------------------------------------------------
# Supplementary inputs
# ---------------------------------------------------------------------------


def test_extra_input_attaches_to_supplementary_data(tmp_path):
    """End-to-end: --extra-input loads JSON and the rule engine sees it."""
    launch = tmp_path / "launch.json"
    launch.write_text(json.dumps({"property": {"name": "Demo"}, "rules": [1, 2]}), encoding="utf-8")
    output = tmp_path / "out.html"
    rc = main([
        str(FIXTURES / "cja_snapshot_clean.json"),
        "--output", str(output),
        "--extra-input", f"launch={launch}",
        "--quiet",
    ])
    assert rc == SUCCESS


def test_extra_input_rejects_malformed_spec(tmp_path):
    output = tmp_path / "out.html"
    rc = main([
        str(FIXTURES / "cja_snapshot_clean.json"),
        "--output", str(output),
        "--extra-input", "no_equals_sign",
        "--quiet",
    ])
    assert rc == RUNTIME_ERROR


def test_extra_input_rejects_missing_file(tmp_path):
    output = tmp_path / "out.html"
    rc = main([
        str(FIXTURES / "cja_snapshot_clean.json"),
        "--output", str(output),
        "--extra-input", f"launch={tmp_path}/no_such.json",
        "--quiet",
    ])
    assert rc == RUNTIME_ERROR


def test_extra_input_rejects_duplicate_keys(tmp_path):
    launch_a = tmp_path / "a.json"
    launch_b = tmp_path / "b.json"
    launch_a.write_text("{}", encoding="utf-8")
    launch_b.write_text("{}", encoding="utf-8")
    rc = main([
        str(FIXTURES / "cja_snapshot_clean.json"),
        "--output", str(tmp_path / "out.html"),
        "--extra-input", f"launch={launch_a}",
        "--extra-input", f"launch={launch_b}",
        "--quiet",
    ])
    assert rc == RUNTIME_ERROR

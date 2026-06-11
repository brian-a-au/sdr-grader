"""Trend report tests — runner, renderer, CLI."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from sdr_grader.cli.exit_codes import RUNTIME_ERROR, SUCCESS
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend import build_trend_report, render_trend
from sdr_grader.trend.renderer import sparkline_svg

FIXTURES = Path(__file__).parent / "fixtures"
STRICT_PACK = Path(__file__).resolve().parent.parent / "src" / "sdr_grader" / "rules" / "packs" / "strict"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_series(tmp_path: Path) -> Path:
    """Materialize a 4-snapshot chronological series of the messy fixture
    where each snapshot fills in a few more descriptions, so the trend
    improves over time.
    """
    base = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    dates = ["2025-12-01", "2026-01-15", "2026-03-01", "2026-04-25"]
    for i, date in enumerate(dates):
        snap = json.loads(json.dumps(base))
        # Fill in i * 10 descriptions on the metrics that originally lacked them.
        fixes = i * 10
        for j, m in enumerate(snap["metrics"][:38]):
            if j < fixes:
                m["description"] = "Backfilled description."
        snap["metadata"]["Generation Timestamp"] = f"{date} 09:14:00"
        (tmp_path / f"snapshot_{date}.json").write_text(json.dumps(snap), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def test_build_trend_report_orders_chronologically(tmp_path):
    _build_series(tmp_path)
    rubric = load_rubric(STRICT_PACK)
    trend = build_trend_report(tmp_path, rubric)
    assert len(trend.points) == 4
    timestamps = [p.timestamp for p in trend.points]
    assert timestamps == sorted(timestamps)
    assert trend.instance_id == "dv_messy_prod_web"
    assert trend.platform == "cja"


def test_build_trend_report_skips_undated_files(tmp_path):
    _build_series(tmp_path)
    # Drop in an undated copy; runner should skip it.
    (tmp_path / "extra.json").write_text(
        (tmp_path / "snapshot_2026-04-25.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    trend = build_trend_report(tmp_path, load_rubric(STRICT_PACK))
    assert len(trend.points) == 4


def test_build_trend_report_rejects_mixed_instances(tmp_path):
    _build_series(tmp_path)
    # Inject a snapshot from a different instance.
    other = json.loads((FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8"))
    other["metadata"]["Generation Timestamp"] = "2026-05-01 09:14:00"
    (tmp_path / "snapshot_2026-05-01.json").write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(InvalidSnapshotError, match="multiple instance IDs"):
        build_trend_report(tmp_path, load_rubric(STRICT_PACK))


def test_build_trend_report_rejects_empty_directory(tmp_path):
    with pytest.raises(InvalidSnapshotError, match="no .json snapshots"):
        build_trend_report(tmp_path, load_rubric(STRICT_PACK))


def test_build_trend_report_rejects_directory_with_only_undated_files(tmp_path):
    base = (FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8")
    (tmp_path / "anonymous.json").write_text(base, encoding="utf-8")
    with pytest.raises(InvalidSnapshotError, match="parseable filename timestamps"):
        build_trend_report(tmp_path, load_rubric(STRICT_PACK))


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def test_render_trend_produces_html_with_expected_sections(tmp_path):
    _build_series(tmp_path)
    trend = build_trend_report(tmp_path, load_rubric(STRICT_PACK))
    html = render_trend(trend)
    assert "<!doctype html>" in html.lower()
    assert "Production Web Analytics" in html  # instance name
    assert 'id="overall-trajectory"' in html
    assert 'class="trend-table"' in html
    assert 'id="churn"' in html


def test_render_trend_self_contained():
    pct_series = [55, 60, 70, 80]
    svg = sparkline_svg(pct_series, width=200, height=50)
    assert "<svg" in svg
    assert "polyline" in svg
    assert "http://" not in svg.replace("xmlns=\"http://www.w3.org/2000/svg\"", "")


def test_sparkline_handles_single_point():
    svg = sparkline_svg([42], width=120, height=30)
    assert "<svg" in svg


def test_render_trend_escapes_untrusted_fields(tmp_path):
    """Instance names come from snapshot data and must be escaped; the
    inlined CSS and server-side sparkline SVG must pass through raw."""
    _build_series(tmp_path)
    trend = build_trend_report(tmp_path, load_rubric(STRICT_PACK))
    evil = dataclasses.replace(trend, instance_name='Acme <script>alert(1)</script>')
    html = render_trend(evil)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    # CSS must survive unescaped...
    assert ".cat .bar > span" in html
    # ...and sparkline SVG must still be inlined raw, not entity-escaped.
    assert "<polyline" in html


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_trend_mode_writes_html(tmp_path):
    series_dir = tmp_path / "snaps"
    series_dir.mkdir()
    _build_series(series_dir)
    out = tmp_path / "trend.html"
    rc = main([
        str(series_dir),
        "--trend",
        "--output", str(out),
        "--quiet",
    ])
    assert rc == SUCCESS
    html = out.read_text(encoding="utf-8")
    assert "trend-table" in html


def test_cli_trend_mode_rejects_non_directory(tmp_path):
    rc = main([
        str(FIXTURES / "cja_snapshot_messy.json"),
        "--trend",
        "--output", str(tmp_path / "out.html"),
    ])
    assert rc == RUNTIME_ERROR


def test_cli_trend_mode_default_output_filename(tmp_path, monkeypatch):
    series_dir = tmp_path / "snaps"
    series_dir.mkdir()
    _build_series(series_dir)
    monkeypatch.chdir(tmp_path)
    rc = main([str(series_dir), "--trend", "--quiet"])
    assert rc == SUCCESS
    # Default pattern: trend-{instance_id}-{YYYYMMDD}.html
    files = sorted(tmp_path.glob("trend-*.html"))
    assert files, "expected default trend output to be created"

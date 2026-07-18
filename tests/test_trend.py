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


def test_trend_renderer_never_imports_the_rule_engine():
    """Spec F28: the trend renderer must work standalone (fresh process)."""
    import subprocess
    import sys

    code = (
        "import sys; import sdr_grader.trend.renderer; "
        "banned = [m for m in ('sdr_grader.core.grader', "
        "'sdr_grader.adapters.cja', 'sdr_grader.adapters.aa', "
        "'sdr_grader.rules.rubric') if m in sys.modules]; "
        "sys.exit(1 if banned else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code])
    assert proc.returncode == 0


def test_trend_dataclasses_reexported_from_runner():
    from sdr_grader.trend import models, runner

    assert runner.TrendPoint is models.TrendPoint
    assert runner.TrendReport is models.TrendReport


def test_dir_lists_the_lazy_entry_point():
    """Spec F43: PEP 562 ``__getattr__`` needs a matching ``__dir__``."""
    import sdr_grader.trend as trend_pkg

    assert "build_trend_report" in dir(trend_pkg)
    assert set(trend_pkg.__all__) <= set(dir(trend_pkg))


def test_unknown_trend_attribute_raises_attribute_error():
    """Issue #18: cover the lazy loader's negative path."""
    import sdr_grader.trend as trend_pkg

    with pytest.raises(AttributeError, match="does_not_exist"):
        trend_pkg.does_not_exist


def test_render_trend_empty_report_raises_clear_error():
    """Spec F29: fabricated empty input gets ValueError, not IndexError."""
    from sdr_grader.trend.models import TrendReport

    empty = TrendReport(
        instance_id="dv_x",
        instance_name="Empty",
        platform="cja",
        pack="strict",
        pack_version="1.0",
        points=[],
    )
    with pytest.raises(ValueError, match="no points"):
        render_trend(empty)


def test_first_and_latest_raise_clear_error_when_empty():
    """Spec F42: property access mirrors the renderer's empty guard."""
    from sdr_grader.trend.models import TrendReport

    empty = TrendReport(
        instance_id="dv_x",
        instance_name="Empty",
        platform="cja",
        pack="strict",
        pack_version="1.0",
        points=[],
    )
    with pytest.raises(ValueError, match="no points"):
        empty.first
    with pytest.raises(ValueError, match="no points"):
        empty.latest


def test_colliding_category_slugs_resolve_first_wins_everywhere(tmp_path):
    """Spec F39: duplicate slugs agree in the header and table rows."""
    from sdr_grader.trend.renderer import _build_view

    _build_series(tmp_path)
    trend = build_trend_report(tmp_path, load_rubric(STRICT_PACK))
    last = trend.points[-1]
    first_cat = last.report.categories[0]
    clash_pct = 1 if first_cat.pct != 1 else 2
    clash = dataclasses.replace(
        first_cat,
        name=first_cat.name.upper(),
        pct=clash_pct,
    )
    extended = dataclasses.replace(
        last.report,
        categories=[*last.report.categories, clash],
    )
    points = [*trend.points[:-1], dataclasses.replace(last, report=extended)]
    view = _build_view(dataclasses.replace(trend, points=points))

    header_pct = view["category_traces"][0]["latest_pct"]
    row_pct = view["rows"][-1]["categories"][0]["pct"]
    assert header_pct == first_cat.pct
    assert row_pct == first_cat.pct
    assert row_pct != clash_pct


def test_trend_table_rows_align_with_header_union(tmp_path):
    """Spec F26: every body row renders one cell per header column."""
    import re

    _build_series(tmp_path)
    trend = build_trend_report(tmp_path, load_rubric(STRICT_PACK))
    # Drop the last category from the first snapshot to simulate a series
    # whose per-snapshot category sets differ.
    first = trend.points[0]
    reduced = dataclasses.replace(
        first.report, categories=first.report.categories[:-1]
    )
    points = [dataclasses.replace(first, report=reduced), *trend.points[1:]]
    html = render_trend(dataclasses.replace(trend, points=points))

    thead = html.split("<thead>")[1].split("</thead>")[0]
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    header_cells = thead.count("<th")
    rows = re.findall(r"<tr>(.*?)</tr>", tbody, flags=re.S)
    assert rows
    for row in rows:
        assert row.count("<td") == header_cells
    assert '<td class="num"></td>' in tbody  # the dropped category's empty cell


def test_every_template_class_has_a_css_rule():
    """Spec F27: the page must not reference classes no stylesheet defines."""
    import re

    from sdr_grader.trend import renderer as trend_renderer

    template_text = (
        Path(trend_renderer.__file__).parent / "templates" / "trend.html.j2"
    ).read_text(encoding="utf-8")
    classes: set[str] = set()
    for match in re.finditer(r'class="([^"]+)"', template_text):
        for token in match.group(1).split():
            if re.fullmatch(r"[a-z][a-z0-9-]*", token):
                classes.add(token)
    # Dynamic classes injected via {{ trend.delta_class }} / {{ cat.delta_class }}:
    classes.update({"trend-up", "trend-down", "trend-flat"})

    css = trend_renderer._css()
    missing = sorted(c for c in classes if f".{c}" not in css)
    assert missing == []


def test_header_classes_have_top_level_css_rules():
    """Spec F27 regression net: the header classes must be styled outside
    any scoped selector — a scoped rule like `.trend-card .delta` must not
    satisfy the bare `.delta` the header uses."""
    import re

    from sdr_grader.trend import renderer as trend_renderer

    header_classes = [
        "report", "report-header", "header-row", "kicker",
        "instance-name", "instance-meta", "grade-block",
        "grade-letter", "grade-pct", "grade-meta", "delta",
    ]
    css = trend_renderer._css()
    missing = [
        cls
        for cls in header_classes
        if not re.search(rf"^\.{re.escape(cls)}[ .{{]", css, flags=re.M)
    ]
    assert missing == []

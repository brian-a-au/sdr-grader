"""Static SVG chart generator tests."""

from __future__ import annotations

from sdr_grader.render.svg import category_comparison_chart, histogram_chart


def test_histogram_declares_font_family_once():
    """Shared presentation attributes belong on a group, not per element."""
    svg = histogram_chart(your_score=72, median=65, p25=50, p75=80)
    assert svg.count("font-family") == 1


def test_histogram_keeps_markers_and_labels():
    svg = histogram_chart(your_score=72, median=65, p25=50, p75=80)
    assert "you · 72" in svg
    assert "median 65" in svg
    assert 'role="img"' in svg
    # p25/p75 band: x = pct * 4
    assert '<rect x="200" y="30" width="120"' in svg


def test_category_comparison_declares_font_family_in_group():
    svg = category_comparison_chart([("Schema hygiene", 72, 65)])
    assert "<g font-family=" in svg
    assert svg.count("font-family") == 1


def test_category_chart_escapes_labels():
    svg = category_comparison_chart([('<script>alert(1)</script>', 50, 60)])
    assert "<script>" not in svg
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg


def test_histogram_tolerates_inverted_percentiles():
    """Spec F37: p25 > p75 must not produce a negative-width rect."""
    svg = histogram_chart(your_score=50, median=40, p25=90, p75=10)
    assert 'width="-' not in svg
    assert '<rect x="40"' in svg and 'width="320"' in svg  # band spans 10..90


def test_histogram_clamps_out_of_range_inputs():
    svg = histogram_chart(your_score=150, median=-5, p25=0, p75=100)
    assert 'cx="400"' in svg          # marker pinned to the right edge
    assert 'x1="0" y1="26"' in svg    # median pinned to the left edge

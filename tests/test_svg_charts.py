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

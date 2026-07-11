"""Display cap for finding component lists (issue #5).

A finding's `components` block is the only unbounded-size path into the
HTML report. `cap_component_items` bounds what the renderer sees while
the `--json` artifact keeps the full list. The cap is a pure, deterministic
Report -> Report transform applied upstream of render().
"""

from __future__ import annotations

from dataclasses import replace

from fixtures.demo_report import build_demo_report
from sdr_grader.render import (
    MAX_COMPONENT_ITEMS,
    Finding,
    FindingBlock,
    cap_component_items,
    render,
)


def _report_with_items(count: int):
    finding = Finding(
        id="TST-001",
        severity="medium",
        category="Test",
        title="test finding",
        body=[
            FindingBlock(kind="paragraph", html="intro paragraph"),
            FindingBlock(
                kind="components",
                items=[f"comp_{i:04d}" for i in range(count)],
            ),
            FindingBlock(kind="section", label="REMEDIATION", body_html="fix it"),
        ],
    )
    return replace(build_demo_report(), findings=[finding])


def test_block_at_or_under_cap_returns_report_unchanged():
    for count in (3, MAX_COMPONENT_ITEMS):
        report = _report_with_items(count)
        assert cap_component_items(report) is report


def test_block_over_cap_truncates_and_appends_trailer():
    report = _report_with_items(MAX_COMPONENT_ITEMS + 3)
    capped = cap_component_items(report)
    body = capped.findings[0].body

    assert len(body) == 4  # paragraph, capped components, trailer, section
    components = body[1]
    assert components.kind == "components"
    assert components.items == [f"comp_{i:04d}" for i in range(MAX_COMPONENT_ITEMS)]
    trailer = body[2]
    assert trailer.kind == "paragraph"
    assert trailer.html == "… and 3 more (see JSON output)"
    assert body[3].kind == "section"  # following blocks keep their order


def test_trailer_formats_thousands_with_separator():
    report = _report_with_items(MAX_COMPONENT_ITEMS + 2961)
    capped = cap_component_items(report)
    assert capped.findings[0].body[2].html == "… and 2,961 more (see JSON output)"


def test_input_report_is_not_mutated():
    report = _report_with_items(MAX_COMPONENT_ITEMS + 3)
    cap_component_items(report)
    assert len(report.findings[0].body) == 3
    assert len(report.findings[0].body[1].items) == MAX_COMPONENT_ITEMS + 3


def test_cap_is_idempotent():
    report = _report_with_items(MAX_COMPONENT_ITEMS + 3)
    once = cap_component_items(report)
    assert cap_component_items(once) is once


def test_rendered_html_shows_capped_count_and_trailer():
    capped = cap_component_items(_report_with_items(MAX_COMPONENT_ITEMS + 3))
    html = render(capped)
    assert f"Affected components ({MAX_COMPONENT_ITEMS})" in html
    assert "… and 3 more (see JSON output)" in html
    assert "comp_0049" in html
    assert "comp_0050" not in html

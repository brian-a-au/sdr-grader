"""Renderer regression tests.

The renderer's output is the visual contract (SPEC §3). These tests guard:

1. **Structural integrity**: expected sections, finding/category counts.
2. **Determinism**: same input -> byte-identical output, twice in a row.
3. **Golden file**: rendered output matches examples/templated-report.html
   exactly. Any visual change must be a deliberate, reviewed regeneration of
   the golden via scripts/generate_examples.py.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from fixtures.demo_report import build_demo_report
from sdr_grader.render import (
    Distribution,
    DistributionChart,
    FindingAction,
    FindingBlock,
    render,
)

GOLDEN = Path(__file__).parent.parent / "examples" / "templated-report.html"

EXPECTED_SECTIONS = [
    'id="tldr"',
    'id="categories"',
    'id="remediations"',
    'id="findings"',
    'id="distribution"',
    'id="methodology"',
]


def test_render_contains_all_sections():
    html = render(build_demo_report())
    for marker in EXPECTED_SECTIONS:
        assert marker in html, f"expected section marker {marker!r} missing from rendered HTML"


def test_render_contains_six_findings():
    html = render(build_demo_report())
    assert html.count('class="finding"') == 6


def test_render_contains_six_categories():
    report = build_demo_report()
    assert len(report.categories) == 6
    html = render(report)
    for category in report.categories:
        assert category.name in html


def test_render_labels_remediation_as_priority_not_predicted_score():
    html = render(build_demo_report())

    assert "Priority weight 6" in html
    assert "pts overall" not in html
    assert "would move the overall grade" not in html


def test_render_is_self_contained():
    html = render(build_demo_report())
    assert "<link rel=\"stylesheet\"" not in html
    assert "<script" not in html
    assert "cdn." not in html


def test_render_is_deterministic():
    a = render(build_demo_report())
    b = render(build_demo_report())
    assert a == b, "renderer must produce byte-identical output for identical input"


def test_render_matches_golden():
    """Output must match examples/templated-report.html byte-for-byte.

    If this fails after an intentional template change, regenerate the golden:
        uv run python scripts/generate_examples.py
    Then review the diff in `examples/templated-report.html` before committing.
    """
    actual = render(build_demo_report())
    expected = GOLDEN.read_text(encoding="utf-8")
    assert actual == expected, (
        "rendered output drifted from examples/templated-report.html. "
        "Regenerate via: uv run python scripts/generate_examples.py"
    )


def test_render_findings_use_content_visibility():
    """Findings are the unbounded section; off-screen ones must be
    layout-skippable so 500-finding reports stay fast to open."""
    html = render(build_demo_report())
    assert "content-visibility: auto" in html
    assert "contain-intrinsic-size" in html
    assert "content-visibility: visible" in html


def test_render_escapes_untrusted_fields():
    """Plain-text fields from snapshots (names, titles) must be HTML-escaped,
    while the inlined CSS must pass through unescaped."""
    report = build_demo_report()
    report.instance_name = 'Acme <script>alert(1)</script> & "Co"'
    html = render(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    # CSS is trusted and must NOT be escaped (child combinator survives).
    assert ".cat .bar > span" in html


class _AttackSurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)


def test_render_keeps_hostile_values_inert_at_every_dynamic_sink():
    payload = (
        '\"><img src="https://attacker.invalid/x" onerror="alert(1)">'
        '<svg onload="alert(2)"><script>alert(3)</script></svg>'
        '<style>body{background:url(file:///private/secret)}</style>'
        "javascript:alert(4)&"
    )
    report = build_demo_report()
    report.instance_name = payload
    report.categories[0].name = payload
    report.categories[0].pct = payload  # type: ignore[assignment]
    report.remediations[0].text = payload
    report.remediations[0].refs = [payload]
    report.findings[0].id = payload
    report.findings[0].category = payload
    report.findings[0].title = payload
    report.findings[0].body = [
        FindingBlock(kind="paragraph", html=payload),
        FindingBlock(kind="section", label=payload, body_html=payload),
        FindingBlock(kind="components", items=[payload]),
        FindingBlock(kind="code", text=payload),
    ]
    report.findings[0].actions = [
        FindingAction(label=payload, href="javascript:alert(5)"),
        FindingAction(label="unsafe file", href="file:///private/secret"),
        FindingAction(label="safe local", href="#methodology"),
    ]
    report.methodology.paragraphs = [payload]  # type: ignore[list-item]
    report.methodology.skipped[0].ids = [payload]
    report.methodology.skipped[0].reason = payload
    report.distribution = Distribution(
        charts=[DistributionChart(label=payload, svg=payload)]  # type: ignore[arg-type]
    )
    report.tool_url = "https://attacker.invalid/source"

    html = render(report)
    parsed = _AttackSurfaceParser()
    parsed.feed(html)

    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert "svg" not in parsed.tags
    assert all(not name.lower().startswith("on") for name, _value in parsed.attributes)
    urls = [
        value
        for name, value in parsed.attributes
        if name.lower() in {"href", "src", "action", "formaction"} and value
    ]
    assert "#methodology" in urls
    assert all(url.startswith("#") for url in urls)
    assert "&lt;img" in html
    assert parsed.tags.count("style") == 1
    assert "Content-Security-Policy" in html
    assert 'content="default-src \'none\';' in html
    assert 'name="referrer" content="no-referrer"' in html


def test_template_and_css_are_cached():
    """render() must not recompile the template or re-read CSS per call."""
    from sdr_grader.render import renderer as renderer_mod
    from sdr_grader.trend import renderer as trend_mod

    assert renderer_mod._template() is renderer_mod._template()
    assert renderer_mod._css() is renderer_mod._css()
    assert trend_mod._template() is trend_mod._template()
    assert trend_mod._css() is trend_mod._css()


def test_naive_and_aware_utc_generated_at_render_identically():
    """Spec F31: fabricated naive datetimes must not depend on the machine tz."""
    import dataclasses
    from datetime import UTC, datetime

    from sdr_grader.render.json_output import report_to_dict

    base = build_demo_report()
    naive = dataclasses.replace(base, generated_at=datetime(2026, 4, 25, 9, 14))
    aware = dataclasses.replace(
        base, generated_at=datetime(2026, 4, 25, 9, 14, tzinfo=UTC)
    )
    assert render(naive) == render(aware)
    assert report_to_dict(naive)["generated_at"] == "2026-04-25T09:14:00Z"

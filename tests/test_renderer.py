"""Renderer regression tests.

The renderer's output is the visual contract (SPEC §3). These tests guard:

1. **Structural integrity**: expected sections, finding/category counts.
2. **Determinism**: same input -> byte-identical output, twice in a row.
3. **Golden file**: rendered output matches examples/templated-report.html
   exactly. Any visual change must be a deliberate, reviewed regeneration of
   the golden via scripts/generate_examples.py.
"""

from __future__ import annotations

import dataclasses
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from markupsafe import Markup

from fixtures.demo_report import build_demo_report
from sdr_grader import __version__
from sdr_grader.render import (
    Distribution,
    DistributionChart,
    FindingAction,
    FindingBlock,
    render,
)
from sdr_grader.render.color_packs import COLOR_PACK_CODES, resolve_color_pack
from sdr_grader.rules.rubric import load_rubric

GOLDEN = Path(__file__).parent.parent / "examples" / "templated-report.html"
STRICT_PACK = (
    Path(__file__).parent.parent / "src" / "sdr_grader" / "rules" / "packs" / "strict"
)

EXPECTED_SECTIONS = [
    'id="tldr"',
    'id="categories"',
    'id="remediations"',
    'id="findings"',
    'id="distribution"',
    'id="methodology"',
]


def _contrast_ratio(first: str, second: str) -> float:
    def relative_luminance(hex_color: str) -> float:
        channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


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


def test_demo_report_uses_current_default_cja_rule_inventory():
    report = build_demo_report()
    rubric = load_rubric(STRICT_PACK)
    default_cja_ids = {
        rule.id for rule in rubric.rules if not rule.platforms or "cja" in rule.platforms
    }
    finding_ids = {finding.id for finding in report.findings}
    remediation_ids = {rule_id for item in report.remediations for rule_id in item.refs}
    suppressed_ids = {
        rule_id for item in report.methodology.skipped for rule_id in item.ids
    }

    assert report.rubric.pack == rubric.pack == "strict"
    assert report.rubric.version == rubric.version == "2.0"
    assert report.tool_version == __version__
    assert len(default_cja_ids) == 27
    assert finding_ids == {
        "ATTR-004",
        "CALC-014",
        "GOV-001",
        "NAME-001",
        "SCH-003",
        "SEG-007",
    }
    assert finding_ids <= default_cja_ids
    assert remediation_ids <= finding_ids
    assert suppressed_ids <= default_cja_ids
    assert suppressed_ids == {"CALC-001", "SEG-005"}
    assert not finding_ids & suppressed_ids
    assert "ATTR-002" not in finding_ids  # registered opt-in check, not a default rule


def test_demo_report_copy_uses_real_audit_path_and_safe_actions():
    report = build_demo_report()
    methodology = " ".join(str(paragraph) for paragraph in report.methodology.paragraphs)
    rendered_blocks = " ".join(
        str(value)
        for finding in report.findings
        for block in finding.body
        for value in (block.html, block.body_html, block.text)
        if value is not None
    )

    assert "stable rule IDs" in methodology
    assert "rubric documentation" in methodology
    assert "repository" in methodology
    assert "source YAML is linked" not in methodology
    assert "source YAML is linked" not in methodology.replace("&rsquo;", "'")
    assert "strict@2.0" in methodology
    assert "73 rules" not in methodology
    assert "self-graded" not in str(report.tldr_html)
    assert "publicly graded" not in str(report.tldr_html)
    assert "--org-report" not in rendered_blocks
    assert "--snapshot" not in rendered_blocks
    assert "--git-init" not in rendered_blocks
    assert "--git-commit" not in rendered_blocks
    assert "--quality-report" not in rendered_blocks
    assert "--include-all-inventory --format json --output" in rendered_blocks
    for finding in report.findings:
        assert finding.actions
        assert all(action.href in {"#methodology", "#remediations"} for action in finding.actions)


def test_demo_distribution_uses_neutral_reference_label():
    report = build_demo_report()
    assert report.distribution is not None
    assert report.distribution.charts[0].label == "Overall score vs reference distribution"


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


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_render_applies_every_color_pack_with_visible_identity(code):
    report = build_demo_report()
    finding = report.findings[0]
    report.findings = [
        dataclasses.replace(finding, id=f"TEST-{index}", severity=severity)
        for index, severity in enumerate(
            ("critical", "high", "medium", "low"),
            start=1,
        )
    ]
    html = render(report, color_pack=code)
    pack = resolve_color_pack(code)

    assert f'data-color-pack="{code}"' in html
    assert f"Color pack: {code}" in html
    assert f"--sdr-accent-primary: {pack.roles['accent-primary']};" in html
    assert "Critical" in html
    assert "High" in html
    assert "Medium" in html
    assert "Low" in html


def test_render_omitted_and_explicit_default_are_byte_identical():
    report = build_demo_report()
    html = render(report)
    assert html == render(report, color_pack="default")
    assert html.index("/* ---------- Reset & base ---------- */") < html.index(":root {")
    for declaration in (
        "--sdr-report-severity-critical: #8B2A1F;",
        "--sdr-report-severity-high: #9C4F10;",
        "--sdr-report-surface-code: #F3F1E8;",
        "--sdr-report-border-code: #C9C5B6;",
        "--sdr-report-trend-card: #F3F1EA;",
    ):
        assert declaration in html


def test_default_high_severity_alias_uses_accessible_shared_text_role():
    from sdr_grader.render.renderer import _renderer_color_value

    pack = resolve_color_pack("default")
    resolved = _renderer_color_value(pack, "severity-high")

    assert resolved == pack.roles["severity-high"] == "#9C4F10"
    assert _contrast_ratio(resolved, pack.roles["surface-panel"]) >= 4.5


@pytest.mark.parametrize("code", COLOR_PACK_CODES[1:])
def test_render_nondefault_pack_is_deterministic(code):
    report = build_demo_report()
    assert render(report, color_pack=code) == render(report, color_pack=code)


def test_render_color_pack_state_does_not_leak_between_calls():
    report = build_demo_report()
    expected_default = render(report)

    render(report, color_pack="ADBE")
    render(report, color_pack="BLUE")

    assert render(report) == expected_default


def test_render_rejects_invalid_color_pack_before_template_work(monkeypatch):
    from sdr_grader.render import renderer as renderer_mod

    monkeypatch.setattr(renderer_mod, "_template", lambda: pytest.fail("template used"))

    with pytest.raises(ValueError, match="available color packs"):
        render(build_demo_report(), color_pack="adbe")


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_distribution_recoloring_is_attribute_scoped_and_preserves_trust(code):
    from sdr_grader.render.renderer import _recolor_distribution_svg

    pack = resolve_color_pack(code)
    trusted = Markup(
        '<svg><text fill="#8a8a82">literal #1a1a1a &lt;em&gt;x&lt;/em&gt;</text>'
        '<text>literal fill="#1a1a1a" stroke="#d8d6cf"</text>'
        '<path fill="#1a1a1a" stroke="#d8d6cf"/>'
        '<rect fill="#ece9e0"/>'
        '<path data-fill="#1a1a1a"/>'
        '<path fill="#ABCDEF"/></svg>'
    )
    plain = (
        '<svg><text fill="#8a8a82">literal #1a1a1a <script>x</script></text>'
        '<path fill="#1a1a1a" stroke="#d8d6cf"/>'
        '<rect fill="#ece9e0"/></svg>'
    )

    recolored_trusted = _recolor_distribution_svg(trusted, pack)
    recolored_plain = _recolor_distribution_svg(plain, pack)

    assert isinstance(recolored_trusted, Markup)
    assert type(recolored_plain) is str
    assert "literal #1a1a1a" in recolored_trusted
    assert 'literal fill="#1a1a1a" stroke="#d8d6cf"' in recolored_trusted
    assert "literal #1a1a1a" in recolored_plain
    assert "&lt;em&gt;x&lt;/em&gt;" in recolored_trusted
    assert "<script>x</script>" in recolored_plain
    assert f'fill="{pack.roles["chart-axis"]}"' in recolored_trusted
    assert f'fill="{pack.roles["chart-primary"]}"' in recolored_trusted
    assert f'stroke="{pack.roles["chart-grid"]}"' in recolored_trusted
    assert f'fill="{pack.roles["chart-grid"]}"' in recolored_trusted
    assert f'fill="{pack.roles["chart-axis"]}"' in recolored_plain
    assert f'fill="{pack.roles["chart-primary"]}"' in recolored_plain
    assert f'stroke="{pack.roles["chart-grid"]}"' in recolored_plain
    assert f'fill="{pack.roles["chart-grid"]}"' in recolored_plain
    assert _contrast_ratio(pack.roles["chart-grid"], pack.roles["surface-page"]) >= 3.0
    assert 'data-fill="#1a1a1a"' in recolored_trusted
    assert 'fill="#ABCDEF"' in recolored_trusted

    report = build_demo_report()
    report.distribution = Distribution(
        charts=[DistributionChart(label="Adversarial", svg=plain)]
    )
    html = render(report, color_pack=code)
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert "literal #1a1a1a" in html


def test_default_distribution_recolors_only_the_rendered_view_for_accessibility():
    import json

    from sdr_grader.render.json_output import report_to_dict

    report = build_demo_report()
    assert report.distribution is not None
    original = report.distribution.charts[0].svg
    original_svg_bytes = str(original).encode()
    original_json_bytes = json.dumps(
        report_to_dict(report), ensure_ascii=False, sort_keys=True
    ).encode()
    pack = resolve_color_pack("default")

    html = render(report, color_pack="default")
    distribution_html = html[
        html.index('<section id="distribution">') : html.index(
            "</section>", html.index('<section id="distribution">')
        )
    ]

    assert str(original) not in distribution_html
    assert re.search(
        rf'<text\b[^>]*\bfill="{pack.roles["chart-axis"]}"',
        distribution_html,
    )
    assert re.search(
        rf'<(?:line|rect)\b[^>]*\b(?:fill|stroke)="{pack.roles["chart-grid"]}"',
        distribution_html,
    )
    assert not re.search(r'<text\b[^>]*\bfill="#8a8a82"', distribution_html, re.IGNORECASE)
    assert not re.search(
        r'<(?:line|rect)\b[^>]*\b(?:fill|stroke)="#ece9e0"',
        distribution_html,
        re.IGNORECASE,
    )
    assert _contrast_ratio(pack.roles["chart-axis"], pack.roles["surface-panel"]) >= 4.5
    assert _contrast_ratio(pack.roles["chart-grid"], pack.roles["surface-panel"]) >= 3.0
    assert str(report.distribution.charts[0].svg).encode() == original_svg_bytes
    assert report.distribution.charts[0].svg is original
    assert (
        json.dumps(report_to_dict(report), ensure_ascii=False, sort_keys=True).encode()
        == original_json_bytes
    )


def test_report_css_uses_semantic_variables_and_pack_aware_print_roles():
    from sdr_grader.render import renderer as renderer_mod
    from sdr_grader.trend.renderer import _trend_css

    css = renderer_mod._css()
    trend_css = _trend_css()
    raw_color = re.compile(r"#[0-9A-Fa-f]{3,8}|rgba?\([^)]*\)")
    assert raw_color.findall(".mutant { color: #ED2224; background: rgb(0, 0, 0); }") == [
        "#ED2224",
        "rgb(0, 0, 0)",
    ]
    assert raw_color.findall(css) == []
    assert raw_color.findall(trend_css) == []
    assert "var(--sdr-report-severity-critical)" in css
    assert "var(--sdr-print-background)" in css
    assert "var(--sdr-print-foreground)" in css
    assert "var(--sdr-print-border)" in css
    assert ".sev" in css and "border: 1px solid currentColor" in css
    assert "color: var(--sdr-border-strong)" not in css
    assert "color: var(--sdr-border-strong)" not in trend_css
    assert "color: var(--sdr-text-muted)" in css
    assert "color: var(--sdr-text-muted)" in trend_css


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

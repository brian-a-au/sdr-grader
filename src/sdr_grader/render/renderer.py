"""sdr-grader report renderer.

Takes a structured Report and produces a single self-contained HTML file.

Design notes
------------
- One render() entry point. No web framework, no async, no JS.
- CSS is read from disk and inlined into the template at render time. The
  output file has no external dependencies; it works offline, it survives
  email attachment, and it renders identically on Windows, macOS, Linux.
- SVG charts are generated server-side from numeric inputs so the output
  is static. No Chart.js, no D3 runtime.
- Severity classes and category bar warning thresholds are computed in
  Python, not in the template, so the template stays declarative.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from sdr_grader import __version__ as _PACKAGE_VERSION
from sdr_grader.render.color_packs import (
    ColorPack,
    resolve_color_pack,
    serialize_color_pack_css,
)
from sdr_grader.render.dates import human_datetime, to_iso_z

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

Severity = Literal["critical", "high", "medium", "low"]

_SEV_CLASS = {"critical": "crit", "high": "high", "medium": "med", "low": "low"}
_SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}


@dataclass
class Adapter:
    platform: str           # "CJA" | "AA"
    tool: str               # "cja_auto_sdr"
    version: str            # "3.5.17"


@dataclass
class Rubric:
    pack: str               # "strict"
    version: str            # "1.2"


@dataclass
class Category:
    name: str
    pct: int                # 0-100
    grade: str              # "B-"


@dataclass(init=False)
class Remediation:
    text: str
    refs: list[str]
    priority_weight: int

    def __init__(
        self,
        text: str,
        refs: list[str] | None = None,
        priority_weight: int | None = None,
        *,
        impact_pts: int | None = None,
    ) -> None:
        if (
            priority_weight is not None
            and impact_pts is not None
            and priority_weight != impact_pts
        ):
            raise ValueError("priority_weight and impact_pts must agree")
        self.text = text
        self.refs = [] if refs is None else refs
        self.priority_weight = (
            priority_weight
            if priority_weight is not None
            else impact_pts if impact_pts is not None else 0
        )

    @property
    def impact_pts(self) -> int:
        """Deprecated 1.2.x compatibility alias for priority_weight."""
        return self.priority_weight

    @impact_pts.setter
    def impact_pts(self, value: int) -> None:
        self.priority_weight = value


@dataclass
class FindingBlock:
    """One block within a finding's body. `kind` selects the renderer."""
    kind: Literal["paragraph", "section", "components", "code"]
    html: str | None = None         # for kind=paragraph (untrusted plain text)
    label: str | None = None        # for kind=section (uppercase label)
    body_html: str | None = None    # for kind=section (untrusted plain text)
    items: list[str] | None = None  # for kind=components (each line is a row)
    text: str | None = None         # for kind=code (raw, displayed as <pre>)


@dataclass
class FindingAction:
    label: str
    href: str


@dataclass
class Finding:
    id: str                 # "CALC-014"
    severity: Severity
    category: str
    title: str
    body: list[FindingBlock]
    actions: list[FindingAction] = field(default_factory=list)


@dataclass
class SkippedRules:
    ids: list[str]
    reason: str


@dataclass
class Methodology:
    paragraphs: list[str | Markup]
    skipped: list[SkippedRules] = field(default_factory=list)


@dataclass
class DistributionChart:
    label: str
    svg: str | Markup                           # only generated Markup is trusted


@dataclass
class Distribution:
    charts: list[DistributionChart]


@dataclass
class Report:
    id: str                                     # "SDR-2026-0425-PROD-WEB"
    instance_name: str                          # "Production Web Analytics"
    instance_id: str                            # "dv_prod_web"
    grade: str                                  # "B-"
    overall_pct: int
    components_evaluated: int
    components_skipped: int
    components_skipped_reason: str | None
    adapter: Adapter
    rubric: Rubric
    generated_at: datetime
    tldr_html: str | Markup                     # only constructed Markup is trusted
    categories: list[Category]
    remediations: list[Remediation]
    findings: list[Finding]
    methodology: Methodology
    distribution: Distribution | None = None
    tool_version: str = _PACKAGE_VERSION
    tool_url: str = "https://github.com/brian-a-au/sdr-grader"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"
_TOOL_URL = "https://github.com/brian-a-au/sdr-grader"
_FRAGMENT_RE = re.compile(r"^#(?:[A-Za-z][A-Za-z0-9_.:-]*)?$")
_SVG_TAG_RE = re.compile(r"<[^<>]+>")
_SVG_COLOR_ATTRIBUTE_RE = re.compile(
    r'(?P<prefix>(?<![A-Za-z0-9_:-])(?:fill|stroke)=")'
    r'(?P<color>#[0-9a-fA-F]{6})(?P<suffix>")'
)

# Default literals preserve the report's pre-feature computed colors except
# where the shared accessibility contract requires a corrected role value.
# Non-default packs bind each renderer-specific compatibility alias back to a
# shared semantic role. This keeps old visual distinctions without expanding
# the mirrored public role schema.
_RENDERER_COLOR_ALIASES = MappingProxyType(
    {
        "text-secondary": ("#2A2A2A", "text-primary"),
        "severity-critical": ("#8B2A1F", "severity-critical"),
        "severity-high": ("#9C4F10", "severity-high"),
        "severity-medium": ("#6B6B1A", "severity-medium"),
        "severity-low": ("#4A4A4A", "severity-low"),
        "change-added": ("#2A5934", "change-added"),
        "surface-code": ("#F3F1E8", "surface-subtle"),
        "border-code": ("#C9C5B6", "border-default"),
        "trend-up": ("#355C2C", "change-added"),
        "trend-down": ("#8B2A1F", "change-removed"),
        "trend-flat": ("#6B6B66", "text-muted"),
        "trend-card": ("#F3F1EA", "surface-subtle"),
        "chart-grid": ("#D8D6CF", "chart-grid"),
        "chart-secondary": ("#8A8A82", "chart-secondary"),
    }
)

_DISTRIBUTION_SVG_ROLE_BY_LITERAL = MappingProxyType(
    {
        "#d8d6cf": "chart-grid",
        "#8a8a82": "chart-axis",
        "#ece9e0": "chart-grid",
        "#6b6b66": "chart-axis",
        "#1a1a1a": "chart-primary",
        "#2a2a2a": "text-primary",
        "#8b2a1f": "severity-critical",
        "#b8651a": "severity-high",
    }
)


@lru_cache(maxsize=1)
def _template():
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env.get_template("report.html.j2")


@lru_cache(maxsize=1)
def _css() -> str:
    return (_STATIC / "report.css").read_text(encoding="utf-8")


def render(report: Report, color_pack: str = "default") -> str:
    """Produce a single self-contained HTML document."""
    pack = resolve_color_pack(color_pack)
    template = _template()
    css = Markup(_css())
    color_pack_css = Markup(_serialize_renderer_color_css(pack))

    # Decorate findings with display metadata so the template stays declarative.
    findings_view = []
    for f in report.findings:
        findings_view.append({
            "id": f.id,
            "anchor": _anchor(f.id),
            "severity_class": _SEV_CLASS[f.severity],
            "severity_label": _SEV_LABEL[f.severity],
            "category": f.category,
            "title": f.title,
            "body": [asdict(b) for b in f.body],
            "actions": [
                {"label": action.label, "href": action.href}
                for action in f.actions
                if _FRAGMENT_RE.fullmatch(action.href)
            ],
        })

    report_view = {
        "id": report.id,
        "instance_name": report.instance_name,
        "instance_id": report.instance_id,
        "grade": report.grade,
        "overall_pct": report.overall_pct,
        "components_evaluated": report.components_evaluated,
        "components_skipped": report.components_skipped,
        "components_skipped_reason": report.components_skipped_reason,
        "adapter": asdict(report.adapter),
        "rubric": asdict(report.rubric),
        "generated_at_iso": to_iso_z(report.generated_at),
        "generated_at_human": human_datetime(report.generated_at),
        "tldr_html": report.tldr_html,
        "categories": [
            {
                "name": category.name,
                "pct": _bounded_pct(category.pct),
                "grade": category.grade,
            }
            for category in report.categories
        ],
        "remediations": [asdict(r) for r in report.remediations],
        "findings": findings_view,
        "methodology": {
            "paragraphs": report.methodology.paragraphs,
            "skipped": [asdict(s) for s in report.methodology.skipped],
        },
        "distribution": {
            "charts": [
                {
                    "label": chart.label,
                    "svg": _recolor_distribution_svg(chart.svg, pack),
                }
                for chart in report.distribution.charts
            ]
        } if report.distribution else None,
        "tool_version": report.tool_version,
        "tool_url": report.tool_url if report.tool_url == _TOOL_URL else None,
    }

    return template.render(
        report=report_view,
        css=css,
        color_pack_code=pack.code,
        color_pack_css=color_pack_css,
    )


def _renderer_color_value(pack: ColorPack, alias: str) -> str:
    """Resolve one documented renderer alias for a specific render call."""
    default_value, role = _RENDERER_COLOR_ALIASES[alias]
    return default_value if pack.code == "default" else pack.roles[role]


def _serialize_renderer_color_css(pack: ColorPack) -> str:
    """Serialize shared roles plus stable grader compatibility aliases."""
    declarations = [
        f"  --sdr-report-{alias}: {_renderer_color_value(pack, alias)};"
        for alias in _RENDERER_COLOR_ALIASES
    ]
    return "\n".join(
        (
            serialize_color_pack_css(pack).rstrip(),
            ":root {",
            *declarations,
            "}",
            "",
        )
    )


def _recolor_distribution_svg(svg: str | Markup, pack: ColorPack) -> str | Markup:
    """Recolor exact renderer-owned SVG attributes without changing trust.

    Report and JSON retain the original SVG object. Only the per-render view
    copy is transformed, and only exact ``fill``/``stroke`` attribute values
    emitted by ``render.svg`` are eligible; text nodes are never searched.
    """
    def replace_attribute(match: re.Match[str]) -> str:
        literal = match.group("color")
        role = _DISTRIBUTION_SVG_ROLE_BY_LITERAL.get(literal)
        if role is None:
            return match.group(0)
        return f"{match.group('prefix')}{pack.roles[role]}{match.group('suffix')}"

    def replace_tag(match: re.Match[str]) -> str:
        return _SVG_COLOR_ATTRIBUTE_RE.sub(replace_attribute, match.group(0))

    recolored = _SVG_TAG_RE.sub(replace_tag, str(svg))
    return Markup(recolored) if isinstance(svg, Markup) else recolored


def _bounded_pct(value: object) -> int:
    """Keep dynamic data out of inline CSS while preserving valid scores."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, min(100, round(value)))


def _anchor(value: str) -> str:
    token = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-")
    return f"finding-{token or 'unknown'}"

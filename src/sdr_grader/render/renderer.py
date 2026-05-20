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

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from sdr_grader import __version__ as _PACKAGE_VERSION

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


@dataclass
class Remediation:
    text: str
    refs: list[str] = field(default_factory=list)
    impact_pts: int = 0


@dataclass
class FindingBlock:
    """One block within a finding's body. `kind` selects the renderer."""
    kind: Literal["paragraph", "section", "components", "code"]
    html: str | None = None         # for kind=paragraph (raw inline HTML allowed)
    label: str | None = None        # for kind=section (uppercase label)
    body_html: str | None = None    # for kind=section (paragraph after label)
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
    paragraphs: list[str]                       # raw inline HTML allowed
    skipped: list[SkippedRules] = field(default_factory=list)


@dataclass
class DistributionChart:
    label: str
    svg: str                                    # raw SVG markup


@dataclass
class Distribution:
    charts: list[DistributionChart]


@dataclass
class Report:
    id: str                                     # "SDR-2026-0425-PROD-WEB"
    instance_name: str                          # "Production Web Analytics"
    grade: str                                  # "B-"
    overall_pct: int
    components_evaluated: int
    components_skipped: int
    components_skipped_reason: str | None
    adapter: Adapter
    rubric: Rubric
    generated_at: datetime
    tldr_html: str                              # raw inline HTML allowed
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


def render(report: Report) -> str:
    """Produce a single self-contained HTML document."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )

    template = env.get_template("report.html.j2")
    css = (_STATIC / "report.css").read_text(encoding="utf-8")

    # Decorate findings with display metadata so the template stays declarative.
    findings_view = []
    for f in report.findings:
        findings_view.append({
            "id": f.id,
            "severity_class": _SEV_CLASS[f.severity],
            "severity_label": _SEV_LABEL[f.severity],
            "category": f.category,
            "title": f.title,
            "body": [asdict(b) for b in f.body],
            "actions": [asdict(a) for a in f.actions],
        })

    report_view = {
        "id": report.id,
        "instance_name": report.instance_name,
        "grade": report.grade,
        "overall_pct": report.overall_pct,
        "components_evaluated": report.components_evaluated,
        "components_skipped": report.components_skipped,
        "components_skipped_reason": report.components_skipped_reason,
        "adapter": asdict(report.adapter),
        "rubric": asdict(report.rubric),
        "generated_at_iso": report.generated_at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "generated_at_human": report.generated_at.astimezone(UTC).strftime("%b %d %Y · %H:%M UTC"),
        "tldr_html": report.tldr_html,
        "categories": [asdict(c) for c in report.categories],
        "remediations": [asdict(r) for r in report.remediations],
        "findings": findings_view,
        "methodology": {
            "paragraphs": report.methodology.paragraphs,
            "skipped": [asdict(s) for s in report.methodology.skipped],
        },
        "distribution": {"charts": [asdict(c) for c in report.distribution.charts]} if report.distribution else None,
        "tool_version": report.tool_version,
        "tool_url": report.tool_url,
    }

    return template.render(report=report_view, css=css)

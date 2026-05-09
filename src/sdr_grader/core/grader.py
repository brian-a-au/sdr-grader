"""Orchestrator: Implementation + Rubric -> render.Report.

The single one-way flow described in SPEC §4:
    input -> adapter -> Implementation -> grader -> Report -> renderer -> HTML

This module is the only place that knows about both the rule engine and the
renderer. Rules write Findings against Implementation; the grader assembles
those findings and the rubric's scoring metadata into a Report the renderer
can consume verbatim.

Determinism is a contract: identical (Implementation, Rubric) input must
produce a byte-identical Report. No `datetime.now()`; timestamps come from
the snapshot.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import escape

from sdr_grader.core.grade_calc import GradeResult, compute_grade
from sdr_grader.core.models import Implementation
from sdr_grader.render import (
    Adapter,
    Category,
    Finding,
    Methodology,
    Remediation,
    Report,
)
from sdr_grader.render import (
    Rubric as RenderRubric,
)
from sdr_grader.rules.engine import run_rules
from sdr_grader.rules.rubric import Rubric, RuleDefinition

TOP_REMEDIATIONS = 5
SEVERITY_TO_IMPACT_PTS = {"critical": 10, "high": 5, "medium": 3, "low": 1}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Stable fallback timestamp when the snapshot has none. Documented so the
# determinism golden never depends on wall-clock state.
_FALLBACK_GENERATED_AT = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

_PLATFORM_NOUN = {"cja": "data view", "aa": "report suite"}
_PLATFORM_TOOL = {"cja": "cja_auto_sdr", "aa": "aa_auto_sdr"}


def grade(impl: Implementation, rubric: Rubric) -> Report:
    """Run the rubric over an Implementation and return a render-ready Report."""
    findings = run_rules(impl, rubric)
    result = compute_grade(rubric, findings)

    generated_at = _resolve_generated_at(impl.snapshot_taken_at)
    components_evaluated = (
        len(impl.metrics) + len(impl.dimensions) + len(impl.derived_fields)
    )
    rules_by_id = {r.id: r for r in rubric.rules}

    return Report(
        id=_report_id(impl, generated_at),
        instance_name=impl.instance_name,
        grade=result.overall_grade,
        overall_pct=result.overall_pct,
        components_evaluated=components_evaluated,
        components_skipped=0,
        components_skipped_reason=None,
        adapter=Adapter(
            platform=impl.platform.upper(),
            tool=_PLATFORM_TOOL.get(impl.platform, "auto_sdr"),
            version=impl.adapter_version,
        ),
        rubric=RenderRubric(pack=rubric.pack, version=rubric.version),
        generated_at=generated_at,
        tldr_html=_build_tldr(impl, rubric, result),
        categories=[_render_category(cs) for cs in result.categories],
        remediations=_derive_remediations(rules_by_id, findings),
        findings=_sort_findings(findings),
        methodology=_build_methodology(rubric, result, findings),
        distribution=None,  # leaderboard data is a v0.4 concern (SPEC §8)
    )


# ---------------------------------------------------------------------------
# Categories and findings
# ---------------------------------------------------------------------------


def _render_category(cs) -> Category:  # type: ignore[no-untyped-def]
    return Category(
        name=_human_category(cs.slug),
        pct=cs.pct,
        grade=cs.grade,
    )


def _sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (SEVERITY_RANK.get(f.severity, 99), f.id),
    )


# ---------------------------------------------------------------------------
# Remediations
# ---------------------------------------------------------------------------


def _derive_remediations(
    rules_by_id: dict[str, RuleDefinition],
    findings: list[Finding],
) -> list[Remediation]:
    """Build top-N remediations from the rules whose findings actually fired."""
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.id, []).append(f)

    items: list[Remediation] = []
    for rule_id, rule_findings in by_rule.items():
        rule = rules_by_id.get(rule_id)
        if not rule or not rule.remediation:
            continue
        severity = rule_findings[0].severity
        items.append(
            Remediation(
                text=_compact_text(rule.remediation),
                refs=[rule_id],
                impact_pts=SEVERITY_TO_IMPACT_PTS.get(severity, 1),
            )
        )

    items.sort(
        key=lambda r: (-r.impact_pts, r.refs[0] if r.refs else ""),
    )
    return items[:TOP_REMEDIATIONS]


# ---------------------------------------------------------------------------
# TL;DR and methodology
# ---------------------------------------------------------------------------


def _build_tldr(impl: Implementation, rubric: Rubric, result: GradeResult) -> str:
    weakest = min(result.categories, key=lambda c: c.pct, default=None)
    pack_pin = f'<span class="mono">{escape(rubric.pack)}@{escape(rubric.version)}</span>'
    components = (
        len(impl.metrics) + len(impl.dimensions) + len(impl.derived_fields)
    )
    parts = [
        f"This implementation graded <strong>{escape(result.overall_grade)}</strong> "
        f"({result.overall_pct}%). The grader evaluated "
        f"{components} components in this {_PLATFORM_NOUN.get(impl.platform, 'instance')} "
        f"using the {pack_pin} rubric pack."
    ]
    if weakest is not None and weakest.rules_failed > 0:
        parts.append(
            f"The largest gap is in <strong>{escape(_human_category(weakest.slug))}</strong> "
            f"({weakest.pct}%); {weakest.rules_failed} of {weakest.rules_total} "
            f"rules in that category fired."
        )
    return " ".join(parts)


def _build_methodology(
    rubric: Rubric, result: GradeResult, findings: list[Finding]
) -> Methodology:
    rule_count = len(rubric.rules)
    fired_count = len({f.id for f in findings})
    category_count = len(result.categories)
    sev_w = rubric.severity_weights

    paragraphs = [
        (
            f'This grade was produced by <span class="mono">sdr-grader</span> '
            f'using the <span class="mono">{escape(rubric.pack)}@{escape(rubric.version)}</span> '
            f"rubric pack. The rubric encodes {rule_count} rule"
            f"{'s' if rule_count != 1 else ''} across {category_count} active "
            f"categor{'ies' if category_count != 1 else 'y'}; {fired_count} fired "
            "against this snapshot. Each rule contributes to a category subtotal "
            f"weighted by severity (critical: {sev_w['critical']}, high: {sev_w['high']}, "
            f"medium: {sev_w['medium']}, low: {sev_w['low']}). Category subtotals "
            "roll up to the overall score using the category weights defined in "
            "the rubric pack."
        ),
        (
            "The grader is rule-based and deterministic — the same input always "
            "produces the same grade. Findings are auditable: every rule's source "
            "YAML is linked from its finding, and rules can be suppressed or "
            'reweighted via a project-level <span class="mono">.sdr-grader.yaml</span>.'
        ),
    ]
    return Methodology(paragraphs=paragraphs, skipped=[])


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _human_category(slug: str) -> str:
    return slug.replace("_", " ").strip()


def _compact_text(text: str) -> str:
    """Collapse YAML-loaded multi-line text into a single line for the report."""
    return " ".join(text.split())


def _resolve_generated_at(snapshot_taken_at: str | None) -> datetime:
    if not snapshot_taken_at:
        return _FALLBACK_GENERATED_AT
    parsed = _parse_timestamp(snapshot_taken_at)
    return parsed or _FALLBACK_GENERATED_AT


def _parse_timestamp(value: str) -> datetime | None:
    """Tolerate a few common timestamp shapes from cja_auto_sdr / aa_auto_sdr."""
    candidate = value.strip().rstrip("Z")
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(candidate, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


_INSTANCE_TOKEN_RE = re.compile(r"[^A-Z0-9]+")


def _report_id(impl: Implementation, generated_at: datetime) -> str:
    instance_token = _INSTANCE_TOKEN_RE.sub("-", impl.instance_id.upper()).strip("-")
    return f"SDR-{generated_at:%Y-%m%d}-{instance_token}"

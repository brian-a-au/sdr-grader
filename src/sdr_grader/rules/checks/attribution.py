"""Attribution coverage checks (ATTR-001..ATTR-003)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import category_display, compact
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import CalculatedMetric, Implementation
    from sdr_grader.rules.engine import RuleContext


_REVENUE_NAME_RE = re.compile(
    r"\b(revenue|conversion|order|booking|sale|signup|subscribe)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# ATTR-001: revenue/conversion metrics with default last-touch and no rationale
# ---------------------------------------------------------------------------


@register_check("attribution_default_last_touch")
def check_attribution_default_last_touch(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    candidates = [cm for cm in impl.calculated_metrics if _looks_revenue(cm)]
    suspects: list[CalculatedMetric] = []
    for cm in candidates:
        model = (cm.attribution_model or "").lower().replace(" ", "-")
        if model and model not in {"", "last-touch", "lasttouch"}:
            continue
        if cm.description and re.search(r"attribution", cm.description, re.IGNORECASE):
            continue
        suspects.append(cm)

    if not suspects:
        return []
    items = [f"{cm.id}  attribution={cm.attribution_model or '—'}" for cm in suspects[:25]]
    paragraph = (
        f"{len(suspects)} revenue / conversion metric{'s default' if len(suspects) != 1 else ' defaults'} "
        "to last-touch attribution without a documented rationale. Last-touch "
        "is appropriate for some use cases but should be a deliberate "
        "choice, not a silent default."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(suspects)} undocumented last-touch metric{'s' if len(suspects) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# ATTR-002: calc metrics where attribution model is not specified
# ---------------------------------------------------------------------------


@register_check("attribution_missing")
def check_attribution_missing(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.30))
    if not impl.calculated_metrics:
        return []
    missing = [cm for cm in impl.calculated_metrics if not cm.attribution_model]
    rate = len(missing) / len(impl.calculated_metrics)
    if rate <= threshold:
        return []
    paragraph = (
        f"{len(missing)} of {len(impl.calculated_metrics)} calculated metrics "
        f"({round(rate * 100)}%) have no attribution model specified. The "
        "platform falls back to its default model, which is silent until a "
        "stakeholder asks why two metrics that look similar disagree."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(missing)} calc metric{'s lack' if len(missing) != 1 else ' lacks'} explicit attribution",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# ATTR-003: inconsistent attribution choices across similar metrics
# ---------------------------------------------------------------------------


@register_check("attribution_inconsistency")
def check_attribution_inconsistency(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Same set of references, different attribution models -> inconsistency."""
    by_refs: dict[frozenset[str], list[tuple[str, str]]] = defaultdict(list)
    for cm in impl.calculated_metrics:
        if not cm.references or not cm.attribution_model:
            continue
        by_refs[frozenset(cm.references)].append((cm.id, cm.attribution_model))

    conflicts: list[tuple[frozenset[str], list[tuple[str, str]]]] = []
    for refs, members in by_refs.items():
        models = {m for _, m in members}
        if len(members) >= 2 and len(models) >= 2:
            conflicts.append((refs, members))

    if not conflicts:
        return []
    items = []
    for _refs, members in conflicts[:25]:
        items.append(", ".join(f"{cid}={model}" for cid, model in members))
    paragraph = (
        f"{len(conflicts)} group{'s of' if len(conflicts) != 1 else ' of'} calculated "
        "metrics share the same input references but disagree on attribution model. "
        "Unless one is intentionally an alternate-attribution variant, this is a "
        "consistency bug waiting to surface in dashboards."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(conflicts)} attribution inconsistency group{'s' if len(conflicts) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_revenue(cm: CalculatedMetric) -> bool:
    return bool(_REVENUE_NAME_RE.search(cm.name) or _REVENUE_NAME_RE.search(cm.id))


def _make_finding(
    ctx: RuleContext, *, title: str, paragraph: str,
    extra_blocks: list[FindingBlock] | None = None,
) -> Finding:
    body: list[FindingBlock] = [FindingBlock(kind="paragraph", html=paragraph)]
    if extra_blocks:
        body.extend(extra_blocks)
    if ctx.remediation:
        body.append(
            FindingBlock(
                kind="section",
                label="How to remediate",
                body_html=compact(ctx.remediation),
            )
        )
    return Finding(
        id=ctx.rule_id,
        severity=ctx.severity,  # type: ignore[arg-type]
        category=category_display(ctx.category),
        title=title,
        body=body,
    )

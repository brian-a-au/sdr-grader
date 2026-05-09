"""Calculated metric maintainability checks (CALC-*)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import (
    all_component_ids,
    all_segment_ids,
    category_display,
    collect_referenced_ids,
    compact,
)
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# CALC-001: missing descriptions
# ---------------------------------------------------------------------------


@register_check("calc_metrics_missing_descriptions")
def check_calc_metrics_missing_descriptions(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.20))
    if not impl.calculated_metrics:
        return []
    missing = [cm for cm in impl.calculated_metrics if not cm.description]
    if not missing:
        return []
    rate = len(missing) / len(impl.calculated_metrics)
    if rate <= threshold:
        return []
    paragraph = (
        f"{len(missing)} of {len(impl.calculated_metrics)} calculated metrics "
        f"({round(rate * 100)}%) lack descriptions. Calculated metrics carry "
        "definitional choices (attribution, allocation, formula assumptions) "
        "that are invisible from the formula alone."
    )
    return [_make_finding(ctx, title=f"{len(missing)} calculated metrics lack descriptions", paragraph=paragraph)]


# ---------------------------------------------------------------------------
# CALC-002: formula references nonexistent components
# ---------------------------------------------------------------------------


@register_check("calc_formula_broken_refs")
def check_calc_formula_broken_refs(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    component_ids = all_component_ids(impl)
    segment_ids = all_segment_ids(impl)
    calc_ids = {cm.id for cm in impl.calculated_metrics}
    known = component_ids | segment_ids | calc_ids

    broken: list[tuple[str, str]] = []  # (calc_id, missing_ref)
    for cm in impl.calculated_metrics:
        for ref in cm.references:
            if ref not in known:
                broken.append((cm.id, ref))

    if not broken:
        return []
    items = [f"{cm_id} -> {missing}" for cm_id, missing in broken[:25]]
    paragraph = (
        f"{len(broken)} calculated metric reference{'s are' if len(broken) != 1 else ' is'} "
        "broken — the formula points at components, segments, or other "
        "calculated metrics that don't exist in this snapshot."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(broken)} broken calculated metric reference{'s' if len(broken) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# CALC-003: formula complexity score exceeds threshold
# ---------------------------------------------------------------------------


@register_check("calc_complexity_threshold")
def check_calc_complexity_threshold(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    max_complexity = float(ctx.params.get("max_complexity", 75.0))
    over = [cm for cm in impl.calculated_metrics if cm.complexity_score > max_complexity]
    if not over:
        return []
    over.sort(key=lambda cm: -cm.complexity_score)
    items = [f"{cm.id}  complexity={cm.complexity_score:.0f}" for cm in over[:25]]
    paragraph = (
        f"{len(over)} calculated metric{'s have' if len(over) != 1 else ' has'} a complexity "
        f"score above the rubric threshold of {max_complexity:.0f}. High-complexity "
        "formulas are hard to review and easy to miscalibrate."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(over)} high-complexity calc metric{'s' if len(over) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# CALC-004: excessive attribution model variety
# ---------------------------------------------------------------------------


@register_check("attribution_model_variety")
def check_attribution_model_variety(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    max_distinct = int(ctx.params.get("max_distinct", 4))
    counts = Counter(
        cm.attribution_model for cm in impl.calculated_metrics if cm.attribution_model
    )
    if len(counts) <= max_distinct:
        return []
    breakdown = ", ".join(f"{model} ({n})" for model, n in counts.most_common())
    paragraph = (
        f"{len(counts)} distinct attribution models in active use across calculated "
        f"metrics; the rubric flags more than {max_distinct}. Each additional model "
        "is a tax on analysts who must remember which metric uses which logic."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(counts)} distinct attribution models in use",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="section", label="Distribution", body_html=breakdown)],
        )
    ]


# ---------------------------------------------------------------------------
# CALC-005: orphan calculated metrics
# ---------------------------------------------------------------------------


@register_check("orphan_calc_metrics")
def check_orphan_calc_metrics(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.50))
    if not impl.calculated_metrics:
        return []
    referenced = collect_referenced_ids(impl)
    orphans = [cm for cm in impl.calculated_metrics if cm.id not in referenced]
    if not orphans:
        return []
    rate = len(orphans) / len(impl.calculated_metrics)
    if rate <= threshold:
        return []
    paragraph = (
        f"{len(orphans)} of {len(impl.calculated_metrics)} calculated metrics "
        f"({round(rate * 100)}%) are not referenced by any other calculated "
        "metric or segment in this snapshot. Orphans accumulate until "
        "consolidation becomes prohibitively expensive."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(orphans)} orphan calculated metric{'s' if len(orphans) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=[cm.id for cm in orphans[:25]])],
        )
    ]


# ---------------------------------------------------------------------------
# CALC-014: near-duplicate calculated metrics (Jaccard >= threshold)
# ---------------------------------------------------------------------------


@register_check("calc_near_duplicates")
def check_calc_near_duplicates(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Pairwise Jaccard over reference sets; fire on pairs >= threshold."""
    threshold = float(ctx.params.get("min_similarity", 0.85))
    metrics = [cm for cm in impl.calculated_metrics if cm.references]
    clusters: dict[frozenset[str], list[str]] = defaultdict(list)
    for cm in metrics:
        clusters[frozenset(cm.references)].append(cm.id)

    suspects = [(refs, ids) for refs, ids in clusters.items() if len(ids) >= 2]
    # Also approximate: pairs with Jaccard >= threshold but not identical.
    refs_seen = list(clusters.keys())
    for i, refs_a in enumerate(refs_seen):
        for refs_b in refs_seen[i + 1:]:
            if not refs_a or not refs_b:
                continue
            jaccard = len(refs_a & refs_b) / len(refs_a | refs_b)
            if jaccard >= threshold and refs_a != refs_b:
                suspects.append((refs_a | refs_b, [*clusters[refs_a], *clusters[refs_b]]))

    if not suspects:
        return []
    items = []
    seen_groups: set[tuple[str, ...]] = set()
    for _refs, ids in suspects:
        key = tuple(sorted(set(ids)))
        if key in seen_groups:
            continue
        seen_groups.add(key)
        items.append(f"{', '.join(key)}")
    paragraph = (
        f"{len(items)} group{'s' if len(items) != 1 else ''} of calculated "
        "metrics have references overlapping at or above the Jaccard "
        f"similarity threshold ({threshold:.2f}). Near-duplicates produce "
        "subtly different numbers in different reports."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(items)} near-duplicate calculated metric group{'s' if len(items) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items[:25])],
        )
    ]


# ---------------------------------------------------------------------------
# CALC-015: identical formula text across distinct calculated metrics
# ---------------------------------------------------------------------------


@register_check("calc_identical_formula_text")
def check_calc_identical_formula_text(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    groups: dict[str, list[str]] = defaultdict(list)
    for cm in impl.calculated_metrics:
        if not cm.formula_text:
            continue
        groups[cm.formula_text.strip().lower()].append(cm.id)
    duplicates = {text: ids for text, ids in groups.items() if len(ids) > 1}
    if not duplicates:
        return []
    items = [
        f"{text!r}: {', '.join(sorted(ids))}"
        for text, ids in sorted(duplicates.items())[:25]
    ]
    paragraph = (
        f"{len(duplicates)} formula text{'s appear' if len(duplicates) != 1 else ' appears'} "
        "verbatim on more than one calculated metric. Identical formulas are a "
        "red flag for accidental copy-paste rather than intentional duplication."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(duplicates)} repeated formula text{'s' if len(duplicates) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# CALC-022: deprecated allocations (stub for v0.1)
# ---------------------------------------------------------------------------


_DEPRECATED_ALLOCATIONS = {"linear-deprecated", "even-deprecated"}


@register_check("calc_deprecated_allocations")
def check_calc_deprecated_allocations(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire on calc metrics still using deprecated allocation values.

    The deprecated set is a placeholder; real values land when CJA / AA
    formally retires named allocations. Operators can override via params.
    """
    deprecated = set(ctx.params.get("deprecated_allocations", _DEPRECATED_ALLOCATIONS))
    hits = [cm for cm in impl.calculated_metrics if cm.allocation in deprecated]
    if not hits:
        return []
    items = [f"{cm.id} allocation={cm.allocation}" for cm in hits[:25]]
    paragraph = (
        f"{len(hits)} calculated metric{'s use' if len(hits) != 1 else ' uses'} a "
        "deprecated allocation value. Deprecated allocations may behave "
        "unpredictably or be removed in a future platform release."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(hits)} deprecated allocation{'s' if len(hits) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

"""Schema hygiene checks (SCH-001..SCH-006).

Each rule is registered by its `check:` name in the YAML rubric; the YAML
names and Python function names are intentionally decoupled so a single
function can serve multiple rule definitions if needed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import (
    all_component_ids,
    all_components,
    all_segment_ids,
    category_display,
    collect_referenced_ids,
    compact,
    join_with_and,
    parse_platform_setting,
    pct,
    platform_noun,
)
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# SCH-003: missing descriptions
# ---------------------------------------------------------------------------


@register_check("missing_descriptions")
def check_missing_descriptions(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when the rate of components missing descriptions exceeds threshold."""
    threshold = float(ctx.params.get("threshold", 0.10))
    targets: list[str] = list(
        ctx.params.get("targets", ["metrics", "dimensions", "derived_fields"])
    )

    breakdown: list[tuple[str, int, int]] = []
    for target in targets:
        components = getattr(impl, target, None)
        if not components:
            continue
        total = len(components)
        missing = sum(1 for c in components if not c.description)
        breakdown.append((target, missing, total))

    over = [(t, m, n) for t, m, n in breakdown if n > 0 and (m / n) > threshold]
    if not over:
        return []

    total_missing = sum(m for _, m, _ in over)
    parts_str = join_with_and([f"{m} {_human_target(t)}" for t, m, _ in over])
    paragraph = (
        f"{parts_str} in this {platform_noun(impl.platform)} have empty "
        '<span class="mono">description</span> fields. Descriptions are the '
        "primary way new analysts and AI agents understand what a component "
        "measures; missing descriptions force readers to infer intent from "
        "names alone, which is frequently wrong."
    )
    distribution = " ".join(
        f"{_human_target(t).title()}: {m} of {n} missing ({pct(m, n)}%)."
        for t, m, n in over
    ) + f" The rubric threshold is {round(threshold * 100)}%."
    return [
        _make_finding(
            ctx,
            title=f"{total_missing} components lack descriptions",
            paragraph=paragraph,
            distribution=distribution,
        )
    ]


# ---------------------------------------------------------------------------
# SCH-001: duplicate component names within the same component type
# ---------------------------------------------------------------------------


@register_check("duplicate_component_names")
def check_duplicate_component_names(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when components within the same type share a `name` value."""
    targets: list[str] = list(
        ctx.params.get("targets", ["metrics", "dimensions", "derived_fields"])
    )
    duplicates: list[tuple[str, str, list[str]]] = []  # (target, name, component_ids)
    for target in targets:
        components = getattr(impl, target, None) or []
        groups: dict[str, list[str]] = defaultdict(list)
        for c in components:
            groups[c.name.strip().lower()].append(c.id)
        for normalized, ids in groups.items():
            if len(ids) > 1:
                duplicates.append((target, normalized, sorted(ids)))

    if not duplicates:
        return []

    duplicates.sort(key=lambda d: (d[0], d[1]))
    items = [
        f"{_human_target(target)}: {name!r} shared by {len(ids)} components ({', '.join(ids)})"
        for target, name, ids in duplicates
    ]
    paragraph = (
        f"{len(duplicates)} component name{'s are' if len(duplicates) != 1 else ' is'} "
        "shared across multiple distinct components. Duplicate names produce subtly "
        "different numbers in different reports and surface as &ldquo;the dashboards "
        "disagree&rdquo; complaints from executives."
    )
    return [
        _make_finding(
            ctx,
            title=(
                f"{len(duplicates)} duplicate component "
                f"{'names' if len(duplicates) != 1 else 'name'}"
            ),
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SCH-002: broken references (segments / calc metrics referencing missing IDs)
# ---------------------------------------------------------------------------


@register_check("broken_references")
def check_broken_references(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when segments or calc metrics reference IDs that don't exist."""
    component_ids = all_component_ids(impl)
    segment_ids = all_segment_ids(impl)
    calc_ids = {cm.id for cm in impl.calculated_metrics}
    known = component_ids | segment_ids | calc_ids

    broken: list[tuple[str, str, str]] = []  # (referrer_type, referrer_id, missing_ref)
    for seg in impl.segments:
        for ref in seg.references:
            if ref not in known:
                broken.append(("segment", seg.id, ref))
    for cm in impl.calculated_metrics:
        for ref in cm.references:
            if ref not in known:
                broken.append(("calc_metric", cm.id, ref))

    if not broken:
        return []

    total = len(broken)
    threshold = int(ctx.params.get("show_top", 10))
    sample = broken[:threshold]
    items = [
        f"{ref_type} {referrer} -> missing {missing}"
        for ref_type, referrer, missing in sample
    ]
    suffix = "" if total <= threshold else f" (showing first {threshold} of {total})"
    paragraph = (
        f"{total} reference{'s are' if total != 1 else ' is'} broken — "
        "segments or calculated metrics point at component IDs that don't "
        f"exist in this {platform_noun(impl.platform)}. Broken references "
        "are usually a symptom of components renamed or deleted without "
        "updating their consumers."
    )
    return [
        _make_finding(
            ctx,
            title=f"{total} broken reference{'s' if total != 1 else ''}{suffix}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SCH-004: type-name mismatches
# ---------------------------------------------------------------------------


_RATE_NAME_RE = re.compile(r"\b(rate|pct|percent|ratio|share)\b", re.IGNORECASE)
# AA event type `counter` stores integers (no decimal); CJA/AEP schemas use
# `integer`/`int`/`long`. A metric whose name implies a rate/percent/ratio
# bound to any of these whole-number types silently truncates to 0%/100%.
#
# Note (2026-05): `counter` is forward-compat scaffolding. The AA 2.0
# Reporting API collapses counter and numeric success events to `INT`
# server-side (per the swagger AnalyticsMetric.type enum: STRING / INT /
# DECIMAL / CURRENCY / PERCENT / TIME / ENUM / ORDERED_ENUM). It will
# only fire if a supplementary admin source — legacy 1.4
# `ReportSuite.GetSuccessEvents` or an admin-console export — supplies
# raw counter values into the snapshot. See docs/RUBRIC_AUDIT.md SCH-004
# row for the corrected wiring trace.
_INTEGER_TYPES = {"integer", "int", "long", "counter"}


@register_check("type_name_mismatch")
def check_type_name_mismatch(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when a metric's name suggests a rate/percent but data_type is integer.

    Best-effort heuristic — naming conventions vary, so this is conservative.
    """
    suspicious: list[tuple[str, str, str]] = []  # (id, name, data_type)
    for m in impl.metrics:
        if not m.data_type:
            continue
        if m.data_type.lower() not in _INTEGER_TYPES:
            continue
        if _RATE_NAME_RE.search(m.name) or _RATE_NAME_RE.search(m.id):
            suspicious.append((m.id, m.name, m.data_type))

    if not suspicious:
        return []

    items = [f"{mid}: name={name!r}, data_type={dtype}" for mid, name, dtype in suspicious]
    plural = len(suspicious) != 1
    paragraph = (
        f"{len(suspicious)} metric{'s have names' if plural else ' has a name'} "
        "implying a rate, percentage, or ratio (which should be a "
        "decimal/float) but the underlying <span class=\"mono\">dataType</span> "
        "is an integer. The metric will round to whole numbers and report 0% "
        "or 100% in most cells."
    )
    title = f"{len(suspicious)} metric type-name mismatch{'es' if plural else ''}"
    return [
        _make_finding(
            ctx,
            title=title,
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SCH-005: deprecated/unused components
# ---------------------------------------------------------------------------


_DEPRECATED_RE = re.compile(
    # `tmp`, `temp`, and `v0` stay removed — their abstract false-positive
    # risks (matches inside `temperature`, `eVar0`, etc.) are real even at
    # word-boundary granularity in some name shapes. `\bold\b` was also
    # dropped in 1c2abf3 on the same reasoning, but corpus vetting (May
    # 2026 audit) showed the named risks (`Order Total`, `Holdovers`) can't
    # actually match `\bold\b` — and the narrowed regex lost 3 genuine
    # `(old)` deprecation flags across 108 fixtures (`Account Name (old)`,
    # `Old Order Status`, `Old Page Type`). `\bold\b` is back.
    r"\b(deprecated|legacy|old|deleteme|do[_\s]?not[_\s]?use)\b",
    re.IGNORECASE,
)
_DEPRECATED_TAGS = {"deprecated", "legacy", "deleteme", "do_not_use"}


@register_check("deprecated_components")
def check_deprecated_components(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when components appear deprecated by name/tag yet remain active.

    A component is "deprecated and active" when it has a deprecated marker
    (tag or name pattern) but is still referenced by something or has been
    modified within the last `stale_days` (defaults to 90).
    """
    referenced = collect_referenced_ids(impl)
    deprecated_active: list[str] = []
    for c in all_components(impl):
        if not _looks_deprecated(c.id, c.name, c.tags):
            continue
        if c.id in referenced:
            deprecated_active.append(c.id)

    if not deprecated_active:
        return []

    items = sorted(deprecated_active)
    paragraph = (
        f"{len(items)} component{'s are' if len(items) != 1 else ' is'} marked "
        "as deprecated (by tag or name) yet still referenced by segments or "
        "calculated metrics in this implementation. Deprecation hasn't "
        "actually completed — consumers are still hitting the old definitions."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(items)} deprecated component{'s' if len(items) != 1 else ''} still in use",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items[:25])],
        )
    ]


def _looks_deprecated(component_id: str, name: str, tags: list[str]) -> bool:
    if any(t.lower() in _DEPRECATED_TAGS for t in tags):
        return True
    return bool(_DEPRECATED_RE.search(name) or _DEPRECATED_RE.search(component_id))


# ---------------------------------------------------------------------------
# SCH-006: cardinality concerns (supplementary-input rule; not in default packs)
# ---------------------------------------------------------------------------


@register_check("cardinality_concerns")
def check_cardinality_concerns(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when dimensions look low-cardinality by name but report many values.

    Reads per-dimension distinct-value counts from
    impl.supplementary_data['cardinality'] when present (a mapping of
    component_id -> int). Operators populate it via --extra-input
    cardinality=PATH where PATH is a JSON object like
    {"variables/evar1": 142}.

    Without that data, the rule is a no-op so it doesn't false-positive.
    """
    cardinalities = impl.supplementary_data.get("cardinality") or {}
    if not isinstance(cardinalities, dict) or not cardinalities:
        return []
    low_cardinality_cap = int(ctx.params.get("low_cardinality_cap", 10))
    keywords = {
        s.lower() for s in (
            ctx.params.get("low_cardinality_keywords") or
            ["boolean", "bool", "flag", "status", "type", "tier"]
        )
    }
    suspects: list[tuple[str, str, int]] = []
    for d in impl.dimensions:
        n = cardinalities.get(d.id)
        if not isinstance(n, int) or n <= low_cardinality_cap:
            continue
        haystack = f"{d.name} {d.data_type or ''}".lower()
        if not any(k in haystack for k in keywords):
            continue
        suspects.append((d.id, d.name, n))

    if not suspects:
        return []
    items = [f"{cid}  name={name!r}  distinct={n}" for cid, name, n in suspects[:25]]
    paragraph = (
        f"{len(suspects)} dimension{'s look' if len(suspects) != 1 else ' looks'} "
        "low-cardinality by name but reports more than "
        f"{low_cardinality_cap} distinct values. Either the schema is wrong, "
        "or upstream is leaking values that should be filtered out before ingest."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(suspects)} cardinality concern{'s' if len(suspects) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SCH-007: persistence lookback exceeds platform cap (CJA-only)
# ---------------------------------------------------------------------------


# Adobe documents 90 days as the maximum lookback for CJA dimension
# persistence. Values beyond that are silently clamped at query time,
# which masks the intended attribution behaviour. See:
# experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/persistence
_DAY_GRANULARITY = {"day", "days"}
_MONTH_GRANULARITY = {"month", "months"}


def _lookback_days(node: dict) -> int | None:
    """Translate an `expiration` or `lookback` block to a day count, or None.

    Only handles the inactivity / lookback-period shapes the platform
    emits today: `{func, granularity, numPeriods}`. Container-based
    expirations (sessions, visitors) and unrecognized shapes return None
    so the rule stays a no-op for them.
    """
    if not isinstance(node, dict):
        return None
    granularity = str(node.get("granularity") or "").lower()
    periods = node.get("numPeriods")
    if not isinstance(periods, (int, float)) or periods <= 0:
        return None
    periods = int(periods)
    if granularity in _DAY_GRANULARITY:
        return periods
    if granularity in _MONTH_GRANULARITY:
        return periods * 30
    return None


@register_check("persistence_lookback_exceeds_cap")
def check_persistence_lookback_cap(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """CJA-only. Fire when a dimension's persistenceSetting encodes a lookback
    longer than Adobe's documented 90-day cap.
    """
    if impl.platform != "cja":
        return []
    cap_days = int(ctx.params.get("cap_days", 90))
    violations: list[tuple[str, str, int]] = []
    for d in impl.dimensions:
        ps = parse_platform_setting(d.platform_specific.get("persistenceSetting"))
        if not ps or not ps.get("enabled"):
            continue
        am = ps.get("allocationModel") or {}
        days = (
            _lookback_days(am.get("expiration"))
            or _lookback_days(ps.get("lookback"))
        )
        if days is not None and days > cap_days:
            violations.append((d.id, d.name, days))

    if not violations:
        return []
    items = [
        f"{cid}  name={name!r}  lookback={days} days"
        for cid, name, days in violations[:25]
    ]
    paragraph = (
        f"{len(violations)} dimension{'s set' if len(violations) != 1 else ' sets'} "
        f"a persistence lookback longer than the platform's {cap_days}-day cap. "
        "Adobe documents 90 days as the maximum for CJA Data View persistence "
        "component settings — values beyond that are silently clamped at query "
        "time, masking the intended attribution behaviour."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(violations)} persistence lookback{'s' if len(violations) != 1 else ''} exceed cap",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# Shared helpers (private)
# ---------------------------------------------------------------------------


def _human_target(target: str) -> str:
    return {
        "metrics": "metrics",
        "dimensions": "dimensions",
        "derived_fields": "derived fields",
    }.get(target, target.replace("_", " "))


def _make_finding(
    ctx: RuleContext,
    *,
    title: str,
    paragraph: str,
    distribution: str | None = None,
    extra_blocks: list[FindingBlock] | None = None,
) -> Finding:
    body: list[FindingBlock] = [FindingBlock(kind="paragraph", html=paragraph)]
    if distribution is not None:
        body.append(FindingBlock(kind="section", label="Distribution", body_html=distribution))
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

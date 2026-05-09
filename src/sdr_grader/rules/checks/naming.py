"""Naming consistency checks (NAME-001..NAME-004)."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import (
    all_components,
    category_display,
    compact,
    pct,
    platform_noun,
)
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Component, Implementation
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# NAME-001: prefix consistency
# ---------------------------------------------------------------------------


_PREFIX_RE = re.compile(r"^([a-z]{1,5}[_-])", re.IGNORECASE)


@register_check("prefix_consistency")
def check_prefix_consistency(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when a component group's prefix consistency falls below threshold."""
    target = ctx.params.get("target", "dimensions")
    tag_filter = ctx.params.get("tag_filter")
    threshold = float(ctx.params.get("min_consistency", 0.80))

    pool = _filter_pool(impl, target, tag_filter)
    if len(pool) < 5:
        return []  # too small to call

    prefixes = [_extract_prefix(c.id) for c in pool]
    counts = Counter([p for p in prefixes if p])
    if not counts:
        return []
    dominant_prefix, dominant_count = counts.most_common(1)[0]
    consistency = dominant_count / len(pool)
    if consistency >= threshold:
        return []

    outliers = [
        c for c, p in zip(pool, prefixes, strict=True) if p != dominant_prefix
    ]
    items = [
        f"{c.id} (expected: {dominant_prefix}{_strip_existing_prefix(c.id)})"
        for c in outliers[:25]
    ]
    paragraph = (
        f"{round(consistency * 100)}% of {_target_display(target, tag_filter)} "
        f"follow the <span class=\"mono\">{dominant_prefix}</span> prefix "
        f"convention. The rubric expects ≥ {round(threshold * 100)}%. "
        f"{len(outliers)} component{'s diverge' if len(outliers) != 1 else ' diverges'} "
        "from the established pattern."
    )
    return [
        _make_finding(
            ctx,
            title=(
                f"Inconsistent prefix convention in "
                f"{_target_display(target, tag_filter)}"
            ),
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)] if items else None,
        )
    ]


# ---------------------------------------------------------------------------
# NAME-002: whitespace / special chars in IDs
# ---------------------------------------------------------------------------


_DEFAULT_ID_PATTERN = r"^[A-Za-z0-9_/.\-]+$"


@register_check("regex_match_id")
def check_regex_match_id(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when component IDs don't match the allowed pattern."""
    pattern_str = ctx.params.get("pattern", _DEFAULT_ID_PATTERN)
    targets: list[str] = list(
        ctx.params.get(
            "targets",
            ["metrics", "dimensions", "derived_fields", "calculated_metrics", "segments"],
        )
    )
    pattern = re.compile(pattern_str)

    violators: list[tuple[str, str]] = []  # (id, target)
    for target in targets:
        items = getattr(impl, target, None) or []
        for item in items:
            if not pattern.match(item.id):
                violators.append((item.id, target))

    if not violators:
        return []

    items = [f"{ident}  ({target})" for ident, target in violators[:25]]
    paragraph = (
        f"{len(violators)} ID{'s do' if len(violators) != 1 else ' does'} not "
        f"match the allowed pattern <span class=\"mono\">{pattern_str}</span>. "
        "Whitespace or special characters in IDs break tooling that splits on "
        "whitespace, embeds IDs in URLs, or stores them as filename fragments."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(violators)} ID{'s' if len(violators) != 1 else ''} fail the ID pattern",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# NAME-003: casing consistency
# ---------------------------------------------------------------------------


@register_check("casing_consistency")
def check_casing_consistency(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when component names mix casing styles beyond a tolerance."""
    target = ctx.params.get("target", "dimensions")
    tag_filter = ctx.params.get("tag_filter")
    threshold = float(ctx.params.get("min_consistency", 0.80))

    pool = _filter_pool(impl, target, tag_filter)
    if len(pool) < 5:
        return []

    styles = [_classify_casing(c.name) for c in pool]
    counts = Counter(s for s in styles if s)
    if not counts:
        return []
    dominant_style, dominant_count = counts.most_common(1)[0]
    consistency = dominant_count / len(pool)
    if consistency >= threshold:
        return []

    outliers = [
        c for c, s in zip(pool, styles, strict=True) if s != dominant_style
    ]
    items = [f"{c.id}  name={c.name!r}" for c in outliers[:25]]
    paragraph = (
        f"{pct(dominant_count, len(pool))}% of "
        f"{_target_display(target, tag_filter)} use {dominant_style}. The "
        f"rubric expects ≥ {round(threshold * 100)}% on a single casing style. "
        f"{len(outliers)} component name{'s diverge' if len(outliers) != 1 else ' diverges'}."
    )
    return [
        _make_finding(
            ctx,
            title=(
                f"Inconsistent casing in {_target_display(target, tag_filter)}"
            ),
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# NAME-004: semantic inconsistency (synonym mixing)
# ---------------------------------------------------------------------------


_DEFAULT_SYNONYM_GROUPS: list[list[str]] = [
    ["user", "visitor"],
    ["page", "screen"],
    ["session", "visit"],
    ["product", "item", "sku"],
    ["customer", "member", "subscriber"],
]


@register_check("semantic_consistency")
def check_semantic_consistency(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when synonyms from the same group appear across the implementation."""
    raw_groups = ctx.params.get("synonym_groups") or _DEFAULT_SYNONYM_GROUPS
    groups: list[list[str]] = [[w.lower() for w in grp] for grp in raw_groups]

    haystack = _names_haystack(impl)
    conflicts: list[tuple[list[str], dict[str, int]]] = []
    for group in groups:
        counts = {word: _count_word(haystack, word) for word in group}
        present = {w: c for w, c in counts.items() if c > 0}
        if len(present) >= 2:
            conflicts.append((group, present))

    if not conflicts:
        return []

    items = []
    for group, counts in conflicts:
        rendered = ", ".join(f"{w}: {c}" for w, c in sorted(counts.items()))
        items.append(f"[{', '.join(group)}] -> {rendered}")
    paragraph = (
        f"{len(conflicts)} synonym group{'s appear' if len(conflicts) != 1 else ' appears'} "
        "in component names with multiple terms in active use. Inconsistent "
        "vocabulary forces analysts to learn each team's idiolect; downstream "
        "tooling and segmentation drift apart over time."
    )
    return [
        _make_finding(
            ctx,
            title=(
                f"Mixed synonym usage in {len(conflicts)} group"
                f"{'s' if len(conflicts) != 1 else ''}"
            ),
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_pool(
    impl: Implementation, target: str, tag_filter: str | None
) -> list[Component]:
    components = getattr(impl, target, None) or []
    if tag_filter:
        return [c for c in components if tag_filter in (c.tags or [])]
    return list(components)


def _extract_prefix(component_id: str) -> str | None:
    # Trim any "namespace/" prefix the platform adds (e.g. variables/, metrics/).
    bare = component_id.rsplit("/", 1)[-1]
    match = _PREFIX_RE.match(bare)
    return match.group(1) if match else None


def _strip_existing_prefix(component_id: str) -> str:
    bare = component_id.rsplit("/", 1)[-1]
    match = _PREFIX_RE.match(bare)
    return bare[match.end():] if match else bare


def _target_display(target: str, tag_filter: str | None) -> str:
    target_label = {
        "metrics": "metrics",
        "dimensions": "dimensions",
        "derived_fields": "derived fields",
    }.get(target, target.replace("_", " "))
    if tag_filter:
        return f"{tag_filter} {target_label}"
    return target_label


_CAMEL_RE = re.compile(r"^[a-z]+(?:[A-Z][a-z0-9]*)+$")
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
_PASCAL_RE = re.compile(r"^(?:[A-Z][a-z0-9]*)+$")
_SCREAMING_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _classify_casing(name: str) -> str | None:
    if not name:
        return None
    stripped = name.strip()
    if not stripped:
        return None
    if " " in stripped:
        # Heuristic: Title Case Words vs lowercase phrases.
        first = stripped.split()[0]
        return "Title Case" if first[:1].isupper() else "lowercase phrase"
    if _CAMEL_RE.match(stripped):
        return "camelCase"
    if _PASCAL_RE.match(stripped):
        return "PascalCase"
    if _SNAKE_RE.match(stripped):
        return "snake_case"
    if _KEBAB_RE.match(stripped):
        return "kebab-case"
    if _SCREAMING_RE.match(stripped):
        return "SCREAMING_SNAKE"
    return None


def _names_haystack(impl: Implementation) -> str:
    parts: list[str] = []
    for c in all_components(impl):
        parts.append(c.name)
        parts.append(c.id)
    for s in impl.segments:
        parts.append(s.name)
    for cm in impl.calculated_metrics:
        parts.append(cm.name)
    return " | ".join(parts).lower()


def _count_word(haystack: str, word: str) -> int:
    return len(re.findall(rf"\b{re.escape(word)}s?\b", haystack))


def _make_finding(
    ctx: RuleContext,
    *,
    title: str,
    paragraph: str,
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


# Quiet linters: platform_noun is exported in case this module grows new rules
# that need it. Suppressing the unused-import nag without removing it is
# cheaper than re-importing later.
_ = platform_noun

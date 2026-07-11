"""Segment complexity checks (SEG-002..SEG-007)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import (
    category_display,
    collect_referenced_ids,
    compact,
    cycle_groups,
)
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation, Segment
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# SEG-002: container type mixing within a single segment
# ---------------------------------------------------------------------------


@register_check("container_mixing")
def check_container_mixing(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire on segments whose definition spans 2+ distinct container contexts."""
    mixed = [s for s in impl.segments if len(set(s.container_types)) >= 2]
    if not mixed:
        return []
    items = [
        f"{s.id}  containers: {', '.join(s.container_types)}  depth: {s.nesting_depth}"
        for s in mixed[:25]
    ]
    paragraph = (
        f"{len(mixed)} segment{'s mix' if len(mixed) != 1 else ' mixes'} "
        "container types (event / session / person) within a single definition. "
        "Mixed containers obscure intent and produce surprising population "
        "differences from segments that look superficially similar."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(mixed)} segment{'s' if len(mixed) != 1 else ''} mix container types",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SEG-003: orphan segments (no references)
# ---------------------------------------------------------------------------


@register_check("orphan_segments")
def check_orphan_segments(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when a high rate of segments aren't referenced by anything we see."""
    threshold = float(ctx.params.get("threshold", 0.50))
    if not impl.segments:
        return []
    referenced = collect_referenced_ids(impl)
    orphans = [s for s in impl.segments if s.id not in referenced]
    if not orphans:
        return []
    rate = len(orphans) / len(impl.segments)
    if rate <= threshold:
        return []
    paragraph = (
        f"{len(orphans)} of {len(impl.segments)} segments "
        f"({round(rate * 100)}%) are not referenced by any other segment "
        "or calculated metric in this snapshot. Orphan segments accumulate "
        "until nobody can tell which are still in use."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(orphans)} orphan segment{'s' if len(orphans) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=[s.id for s in orphans[:25]])],
        )
    ]


# ---------------------------------------------------------------------------
# SEG-004: circular segment references
# ---------------------------------------------------------------------------


@register_check("circular_segments")
def check_circular_segments(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Detect any segment whose reference graph contains a cycle."""
    graph: dict[str, list[str]] = {
        s.id: sorted({ref for ref in s.references if ref.startswith("segments/")})
        for s in impl.segments
    }
    groups = cycle_groups(graph)
    if not groups:
        return []
    items = [", ".join(group) for group in groups[:10]]
    paragraph = (
        f"{len(groups)} cycle{'s' if len(groups) != 1 else ''} detected in the "
        "segment reference graph. Circular references break linear evaluation "
        "and produce inconsistent populations between platform UI and exports."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(groups)} circular segment reference{'s' if len(groups) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SEG-005: segments lacking descriptions
# ---------------------------------------------------------------------------


@register_check("segments_missing_descriptions")
def check_segments_missing_descriptions(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.30))
    if not impl.segments:
        return []
    missing = [s for s in impl.segments if not s.description]
    if not missing:
        return []
    rate = len(missing) / len(impl.segments)
    if rate <= threshold:
        return []
    paragraph = (
        f"{len(missing)} of {len(impl.segments)} segments "
        f"({round(rate * 100)}%) lack descriptions. Segment intent is "
        "exactly the kind of audience-defining decision that must be "
        "documented."
    )
    suffix = "s lack" if len(missing) != 1 else " lacks"
    return [
        _make_finding(
            ctx,
            title=f"{len(missing)} segment{suffix} descriptions",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# SEG-006: identical / duplicate segment definitions
# ---------------------------------------------------------------------------


@register_check("duplicate_segments")
def check_duplicate_segments(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Group segments by canonical definition signature; fire on collisions."""
    groups: dict[str, list[Segment]] = {}
    for s in impl.segments:
        signature = json.dumps(s.definition, sort_keys=True)
        groups.setdefault(signature, []).append(s)

    duplicates = [grp for grp in groups.values() if len(grp) > 1]
    if not duplicates:
        return []
    items = [
        f"{', '.join(s.id for s in grp)}  ({len(grp)} segments share definition)"
        for grp in duplicates[:25]
    ]
    paragraph = (
        f"{len(duplicates)} group{'s' if len(duplicates) != 1 else ''} of "
        "segments share an identical definition. Duplicate segments fragment "
        "the audience library and make consolidation harder."
    )
    return [
        _make_finding(
            ctx,
            title=(
                f"{len(duplicates)} duplicate segment definition group"
                f"{'s' if len(duplicates) != 1 else ''}"
            ),
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


# ---------------------------------------------------------------------------
# SEG-007: nesting depth exceeds threshold
# ---------------------------------------------------------------------------


@register_check("segment_nesting_depth")
def check_segment_nesting_depth(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    max_depth = int(ctx.params.get("max_depth", 4))
    deep = sorted(
        [s for s in impl.segments if s.nesting_depth > max_depth],
        key=lambda s: -s.nesting_depth,
    )
    if not deep:
        return []
    items = [
        f"{s.id}  depth: {s.nesting_depth}  containers: {', '.join(s.container_types) or '-'}"
        for s in deep[:25]
    ]
    paragraph = (
        f"{len(deep)} segment{'s exceed' if len(deep) != 1 else ' exceeds'} the "
        f"nesting depth threshold of {max_depth}. Deep nesting makes intent "
        "illegible — small definitional changes have unpredictable population "
        "effects."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(deep)} segment{'s' if len(deep) != 1 else ''} exceed nesting threshold",
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

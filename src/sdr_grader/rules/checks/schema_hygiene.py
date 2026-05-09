"""Schema hygiene checks.

Phase 3 implements just SCH-003 (missing descriptions) end-to-end.
SCH-001/002/004/005/006 land in Phase 4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


@register_check("missing_descriptions")
def check_missing_descriptions(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when the rate of components missing descriptions exceeds threshold.

    Params:
        threshold: float in 0..1, defaults to 0.10.
        targets: list of attribute names on Implementation to check.
                 Defaults to ["metrics", "dimensions", "derived_fields"].
    """
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

    over_threshold = [
        (target, missing, total)
        for target, missing, total in breakdown
        if total > 0 and (missing / total) > threshold
    ]
    if not over_threshold:
        return []

    total_missing = sum(missing for _, missing, _ in over_threshold)
    parts = [f"{missing} {_human_target(target)}" for target, missing, _ in over_threshold]
    parts_str = _join_with_and(parts)

    paragraph = (
        f"{parts_str} in this {_platform_noun(impl.platform)} have empty "
        '<span class="mono">description</span> fields. Descriptions are the '
        "primary way new analysts and AI agents understand what a component "
        "measures; missing descriptions force readers to infer intent from "
        "names alone, which is frequently wrong."
    )

    distribution_lines = [
        f"{_human_target(target).title()}: {missing} of {total} missing "
        f"({_pct(missing, total)}%)."
        for target, missing, total in over_threshold
    ]
    distribution = (
        " ".join(distribution_lines)
        + f" The rubric threshold is {_pct_from_fraction(threshold)}%."
    )

    body: list[FindingBlock] = [
        FindingBlock(kind="paragraph", html=paragraph),
        FindingBlock(kind="section", label="Distribution", body_html=distribution),
    ]
    if ctx.remediation:
        body.append(
            FindingBlock(
                kind="section",
                label="How to remediate",
                body_html=_format_text(ctx.remediation),
            )
        )

    return [
        Finding(
            id=ctx.rule_id,
            severity=ctx.severity,  # type: ignore[arg-type]
            category=_category_display(ctx.category),
            title=f"{total_missing} components lack descriptions",
            body=body,
        )
    ]


# ---------------------------------------------------------------------------
# Helpers (kept private; rules should compose pure logic, not share UI helpers)
# ---------------------------------------------------------------------------


def _human_target(target: str) -> str:
    return {
        "metrics": "metrics",
        "dimensions": "dimensions",
        "derived_fields": "derived fields",
    }.get(target, target.replace("_", " "))


def _platform_noun(platform: str) -> str:
    return {"cja": "data view", "aa": "report suite"}.get(platform, "instance")


def _category_display(slug: str) -> str:
    return slug.replace("_", " ")


def _pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return round(numerator / denominator * 100)


def _pct_from_fraction(fraction: float) -> int:
    return round(fraction * 100)


def _join_with_and(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _format_text(text: str) -> str:
    """Convert a YAML-loaded multi-line string into a single-paragraph HTML body."""
    return " ".join(text.split())

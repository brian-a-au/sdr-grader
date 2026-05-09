"""Shared helpers for rules/checks/*.

Per SPEC §6: check functions stay self-contained, but truly cross-cutting
formatting + iteration helpers belong here so each check module doesn't
re-derive the same conventions.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdr_grader.core.models import Component, Implementation


PLATFORM_NOUN = {"cja": "data view", "aa": "report suite"}


def category_display(slug: str) -> str:
    """Convert a rubric category slug to its human display name."""
    return slug.replace("_", " ")


def platform_noun(platform: str) -> str:
    return PLATFORM_NOUN.get(platform, "instance")


def all_components(impl: Implementation) -> list[Component]:
    """Metrics + dimensions + derived fields, in a stable order."""
    return [*impl.metrics, *impl.dimensions, *impl.derived_fields]


def all_component_ids(impl: Implementation) -> set[str]:
    return {c.id for c in all_components(impl)}


def all_calc_metric_ids(impl: Implementation) -> set[str]:
    return {cm.id for cm in impl.calculated_metrics}


def all_segment_ids(impl: Implementation) -> set[str]:
    return {s.id for s in impl.segments}


def collect_referenced_ids(impl: Implementation) -> set[str]:
    """Every component / segment / calc metric ID referenced by anything in impl."""
    referenced: set[str] = set()
    for seg in impl.segments:
        referenced.update(seg.references)
    for cm in impl.calculated_metrics:
        referenced.update(cm.references)
    return referenced


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return round(numerator / denominator * 100)


def join_with_and(parts: Iterable[str]) -> str:
    parts = list(parts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def compact(text: str) -> str:
    """Collapse a YAML-loaded multi-line string into a single line."""
    return " ".join(text.split())

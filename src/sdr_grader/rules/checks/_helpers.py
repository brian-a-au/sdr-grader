"""Shared helpers for rules/checks/*.

Per SPEC §6: check functions stay self-contained, but truly cross-cutting
formatting + iteration helpers belong here so each check module doesn't
re-derive the same conventions.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

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


def parse_platform_setting(value: Any) -> dict[str, Any] | None:
    """Parse a CJA Data View setting value into a dict.

    `cja_auto_sdr` ships fields like `persistenceSetting` and
    `attributionSetting` as JSON-encoded strings (e.g.
    `'{"enabled": true, ...}'`) — or as the float `NaN` when the snapshot
    pandas pipeline encountered a missing value. Returns the parsed dict
    on success, or `None` for any value the rule should skip.
    """
    if value is None or value == "":
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def cycle_groups(graph: dict[str, list[str]]) -> list[list[str]]:
    """Strongly connected components of size >= 2, plus self-loops.

    Iterative Tarjan over sorted nodes and sorted, deduplicated
    neighbors, so the result is byte-stable no matter how the caller
    assembled the graph (sets, dicts, any insertion order). Each group
    is sorted; groups sort by first member. Edges pointing outside the
    graph's key set are ignored. Iterative so reference chains deeper
    than the recursion limit cannot crash a grading run.
    """
    nodes = sorted(graph)
    edges = {node: sorted(set(graph.get(node, []))) for node in nodes}

    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    groups: list[list[str]] = []
    counter = 0

    for root in nodes:
        if root in index_of:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, edge_idx = work.pop()
            if edge_idx == 0:
                index_of[node] = counter
                lowlink[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            descended = False
            neighbors = edges[node]
            for i in range(edge_idx, len(neighbors)):
                nxt = neighbors[i]
                if nxt not in edges:
                    continue
                if nxt not in index_of:
                    work.append((node, i + 1))
                    work.append((nxt, 0))
                    descended = True
                    break
                if nxt in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[nxt])
            if descended:
                continue
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index_of[node]:
                group: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                if len(group) > 1 or node in edges[node]:
                    groups.append(sorted(group))
    groups.sort()
    return groups

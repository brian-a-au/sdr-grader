"""AA adapter: aa_auto_sdr JSON output -> normalized Implementation.

Per SPEC §5: eVars and props both map to dimensions (with platform_specific
preserving allocation/expiration/prop-specific flags); events map to metrics;
classifications attach as tags on the parent dimension.
"""

from __future__ import annotations

from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.models import (
    CalculatedMetric,
    Component,
    Implementation,
    Segment,
)


def adapt(snapshot: dict[str, Any], *, source: str = "<unknown>") -> Implementation:
    """Convert a parsed aa_auto_sdr JSON snapshot into an Implementation."""
    if not isinstance(snapshot, dict):
        raise InvalidSnapshotError(
            f"expected top-level JSON object, got {type(snapshot).__name__}"
        )

    if "report_suite" in snapshot:
        rs = snapshot["report_suite"]
    elif "reportSuite" in snapshot:
        rs = snapshot["reportSuite"]
    else:
        raise InvalidSnapshotError(
            "AA snapshot missing 'report_suite' object; not an AA snapshot?"
        )
    if not isinstance(rs, dict):
        raise InvalidSnapshotError(
            f"AA snapshot 'report_suite' must be an object; got {type(rs).__name__}"
        )
    instance_id = rs.get("rsid") or rs.get("RSID")
    if not instance_id:
        raise InvalidSnapshotError("AA snapshot 'report_suite' missing 'rsid'")
    instance_name = rs.get("name") or instance_id
    snapshot_taken_at = snapshot.get("captured_at") or snapshot.get("captured")
    if isinstance(snapshot_taken_at, str):
        snapshot_taken_at = snapshot_taken_at.strip() or None
    adapter_version = str(snapshot.get("tool_version") or "unknown")

    dims_raw = _ensure_list(snapshot, "dimensions")
    metrics_raw = _ensure_list(snapshot, "metrics")
    classifications_by_parent = _index_classifications(snapshot.get("classifications"))

    dimensions = [
        _component_from_record(r, "dimension", classifications_by_parent)
        for r in dims_raw
    ]
    metrics = [
        _component_from_record(r, "metric", classifications_by_parent)
        for r in metrics_raw
    ]
    calculated_metrics = [
        _calc_from_record(r) for r in (snapshot.get("calculated_metrics") or [])
    ]
    segments = [_segment_from_record(r) for r in (snapshot.get("segments") or [])]

    return Implementation(
        platform="aa",
        instance_id=str(instance_id),
        instance_name=str(instance_name),
        snapshot_taken_at=snapshot_taken_at,
        snapshot_source=source,
        adapter_version=adapter_version,
        metrics=metrics,
        dimensions=dimensions,
        segments=segments,
        calculated_metrics=calculated_metrics,
        derived_fields=[],  # CJA-only concept
        raw=snapshot,
    )


# ---------------------------------------------------------------------------
# Components (dimensions and metrics)
# ---------------------------------------------------------------------------


def _component_from_record(
    record: Any, component_type: str, classifications_by_parent: dict[str, list[str]]
) -> Component:
    if not isinstance(record, dict):
        raise InvalidSnapshotError(
            f"expected {component_type} record to be an object, got {type(record).__name__}"
        )
    component_id = record.get("id")
    if not component_id:
        raise InvalidSnapshotError(f"{component_type} record is missing 'id': {record!r}")

    name = record.get("name") or component_id
    description = _normalize_description(record.get("description"))
    data_type = record.get("type")
    polarity = _normalize_polarity(record.get("polarity"))
    tags = list(record.get("tags") or [])
    # Pick up classifications attached to this component as tags.
    extra_class_tags = classifications_by_parent.get(str(component_id), [])
    if extra_class_tags:
        tags = sorted(set([*tags, *extra_class_tags]))

    handled = {"id", "name", "description", "type", "polarity", "tags"}
    platform_specific = {k: v for k, v in record.items() if k not in handled}

    return Component(
        id=str(component_id),
        name=str(name),
        description=description,
        component_type=component_type,  # type: ignore[arg-type]
        data_type=str(data_type) if data_type else None,
        polarity=polarity,
        created_at=record.get("created"),
        modified_at=record.get("modified"),
        owner=str(record.get("owner_id")) if record.get("owner_id") else None,
        tags=tags,
        platform_specific=platform_specific,
    )


def _index_classifications(classifications: Any) -> dict[str, list[str]]:
    """AA classifications attach to a parent dimension by ID; surface as tags."""
    out: dict[str, list[str]] = {}
    if not isinstance(classifications, list):
        return out
    for entry in classifications:
        if not isinstance(entry, dict):
            continue
        parent = entry.get("parent")
        if not parent:
            continue
        out.setdefault(str(parent), []).append(str(entry.get("name") or entry.get("id") or ""))
    return out


# ---------------------------------------------------------------------------
# Calculated metrics
# ---------------------------------------------------------------------------


def _calc_from_record(record: Any) -> CalculatedMetric:
    if not isinstance(record, dict):
        raise InvalidSnapshotError(
            f"expected calculated metric to be an object, got {type(record).__name__}"
        )
    metric_id = record.get("id")
    if not metric_id:
        raise InvalidSnapshotError(f"calc metric missing 'id': {record!r}")
    name = record.get("name") or metric_id
    description = _normalize_description(record.get("description"))
    definition = record.get("definition") or {}
    formula = definition.get("formula") if isinstance(definition, dict) else {}
    formula_text = ""
    if isinstance(formula, dict):
        func = formula.get("func")
        args = formula.get("args") or []
        if isinstance(args, list):
            formula_text = f"{func}({', '.join(str(a) for a in args)})" if func else ""
    references = _extract_aa_calc_refs(formula)

    return CalculatedMetric(
        id=str(metric_id),
        name=str(name),
        description=description,
        formula=formula if isinstance(formula, dict) else {},
        formula_text=formula_text,
        attribution_model=record.get("attribution") or record.get("attribution_model"),
        allocation=record.get("allocation"),
        complexity_score=float(record.get("complexity_score") or 0.0),
        references=references,
        created_at=record.get("created") or record.get("created_at"),
        modified_at=record.get("modified") or record.get("modified_at"),
        owner=str(record.get("owner_id")) if record.get("owner_id") else None,
    )


_AA_REF_PREFIXES = ("metrics/", "variables/", "segments/", "calculatedMetrics/")


def _extract_aa_calc_refs(formula: Any) -> list[str]:
    """Walk an AA calc-metric formula and collect referenced component IDs.

    Recognized prefixes: metrics/, variables/, segments/, calculatedMetrics/.
    The cross-reference IDs let orphan checks see calc-metric→segment and
    calc-metric→calc-metric links instead of treating every component as
    unreferenced.
    """
    refs: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            args = node.get("args")
            if isinstance(args, list):
                for arg in args:
                    if isinstance(arg, str) and arg.startswith(_AA_REF_PREFIXES):
                        if arg not in seen:
                            seen.add(arg)
                            refs.append(arg)
                    else:
                        walk(arg)
            for value in node.values():
                if value is args:
                    continue
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(formula)
    return refs


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


def _segment_from_record(record: Any) -> Segment:
    if not isinstance(record, dict):
        raise InvalidSnapshotError(
            f"expected segment to be an object, got {type(record).__name__}"
        )
    segment_id = record.get("id")
    if not segment_id:
        raise InvalidSnapshotError(f"segment missing 'id': {record!r}")
    name = record.get("name") or segment_id
    description = _normalize_description(record.get("description"))
    definition = record.get("definition") or {}
    nesting_depth, container_types = _walk_segment_definition(definition)
    references: list[str] = []  # AA segments don't expose direct cross-refs in the basic shape

    return Segment(
        id=str(segment_id),
        name=str(name),
        description=description,
        definition=definition if isinstance(definition, dict) else {},
        nesting_depth=nesting_depth,
        container_types=container_types,
        references=references,
        created_at=record.get("created"),
        modified_at=record.get("modified"),
        owner=str(record.get("owner_id")) if record.get("owner_id") else None,
    )


def _walk_segment_definition(definition: Any) -> tuple[int, list[str]]:
    """Compute nesting depth and distinct container contexts from an AA segment def."""
    contexts: list[str] = []
    seen: set[str] = set()

    def visit(node: Any, depth: int) -> int:
        max_depth = depth
        if isinstance(node, dict):
            if node.get("func") == "container" and node.get("context"):
                ctx = str(node["context"])
                if ctx not in seen:
                    seen.add(ctx)
                    contexts.append(ctx)
                max_depth = max(max_depth, depth + 1)
            for value in node.values():
                max_depth = max(max_depth, visit(value, depth + 1))
        elif isinstance(node, list):
            for item in node:
                max_depth = max(max_depth, visit(item, depth + 1))
        return max_depth

    return visit(definition, 0), contexts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_list(snapshot: dict[str, Any], key: str) -> list[Any]:
    value = snapshot.get(key) or []
    if not isinstance(value, list):
        raise InvalidSnapshotError(
            f"AA snapshot '{key}' must be a list, got {type(value).__name__}"
        )
    return value


def _normalize_description(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped == "-":
        return None
    return stripped


def _normalize_polarity(value: Any):
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in {"positive", "negative", "neutral"}:
        return lowered  # type: ignore[return-value]
    return None

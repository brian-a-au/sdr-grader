"""Tests for SCH-001/002/004/005/006 (Phase 4 additions)."""

from __future__ import annotations

from typing import Any

from sdr_grader.core.models import (
    CalculatedMetric,
    Component,
    Implementation,
    Segment,
)
from sdr_grader.rules.checks.schema_hygiene import (
    check_broken_references,
    check_cardinality_concerns,
    check_deprecated_components,
    check_duplicate_component_names,
    check_type_name_mismatch,
)
from sdr_grader.rules.engine import RuleContext


def _component(idx: int, *, name: str | None = None, cid: str | None = None,
               comp_type: str = "metric", data_type: str = "integer",
               tags: list[str] | None = None) -> Component:
    return Component(
        id=cid or f"metrics/m_{idx:03d}",
        name=name or f"Metric {idx:03d}",
        description="ok",
        component_type=comp_type,  # type: ignore[arg-type]
        data_type=data_type,
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=None,
        tags=tags or [],
    )


def _segment(sid: str, refs: list[str]) -> Segment:
    return Segment(
        id=sid,
        name=sid,
        description=None,
        definition={},
        nesting_depth=1,
        container_types=["event"],
        references=refs,
    )


def _calc(cid: str, refs: list[str]) -> CalculatedMetric:
    return CalculatedMetric(
        id=cid,
        name=cid,
        description=None,
        formula={},
        formula_text="",
        attribution_model=None,
        allocation=None,
        complexity_score=10.0,
        references=refs,
    )


def _impl(*, metrics=None, dimensions=None, derived=None, segments=None, calc=None) -> Implementation:
    return Implementation(
        platform="cja",
        instance_id="dv_t",
        instance_name="t",
        snapshot_taken_at=None,
        snapshot_source="t",
        adapter_version="0",
        metrics=metrics or [],
        dimensions=dimensions or [],
        segments=segments or [],
        calculated_metrics=calc or [],
        derived_fields=derived or [],
        raw={},
    )


def _ctx(rule_id: str, severity: str = "medium", **params: Any) -> RuleContext:
    return RuleContext(
        rule_id=rule_id,
        rule_name=rule_id,
        severity=severity,
        category="schema_hygiene",
        platforms=["cja", "aa"],
        params=params,
    )


# ---------------------------------------------------------------------------
# SCH-001 duplicates
# ---------------------------------------------------------------------------


def test_duplicate_names_passes_when_unique():
    metrics = [_component(i, name=f"Unique {i}") for i in range(5)]
    findings = check_duplicate_component_names(_impl(metrics=metrics), _ctx("SCH-001"))
    assert findings == []


def test_duplicate_names_fires_on_collision():
    metrics = [
        _component(1, name="Page Views", cid="metrics/pv1"),
        _component(2, name="Page Views", cid="metrics/pv2"),
        _component(3, name="Distinct"),
    ]
    findings = check_duplicate_component_names(_impl(metrics=metrics), _ctx("SCH-001"))
    assert len(findings) == 1
    assert "1 duplicate component name" in findings[0].title
    assert "page views" in findings[0].body[1].items[0].lower()


def test_duplicate_names_normalizes_case_and_whitespace():
    metrics = [
        _component(1, name="Page Views"),
        _component(2, name="page views  "),
    ]
    findings = check_duplicate_component_names(_impl(metrics=metrics), _ctx("SCH-001"))
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# SCH-002 broken references
# ---------------------------------------------------------------------------


def test_broken_references_passes_when_all_resolve():
    metrics = [_component(1, cid="metrics/visits"), _component(2, cid="metrics/orders")]
    calc = [_calc("calculatedMetrics/x", refs=["metrics/visits", "metrics/orders"])]
    findings = check_broken_references(_impl(metrics=metrics, calc=calc), _ctx("SCH-002", severity="high"))
    assert findings == []


def test_broken_references_fires_on_missing_target():
    metrics = [_component(1, cid="metrics/visits")]
    calc = [_calc("calculatedMetrics/x", refs=["metrics/visits", "metrics/missing"])]
    segs = [_segment("segments/s", refs=["variables/missing_dim"])]
    findings = check_broken_references(
        _impl(metrics=metrics, calc=calc, segments=segs), _ctx("SCH-002", severity="high"),
    )
    assert len(findings) == 1
    assert "2 broken references" in findings[0].title


def test_broken_references_truncates_to_show_top():
    calc = [_calc(f"calc/{i}", refs=[f"missing/{i}"]) for i in range(15)]
    findings = check_broken_references(_impl(calc=calc), _ctx("SCH-002", severity="high", show_top=5))
    assert "showing first 5 of 15" in findings[0].title


# ---------------------------------------------------------------------------
# SCH-004 type-name mismatch
# ---------------------------------------------------------------------------


def test_type_name_mismatch_fires_on_rate_named_integer_metric():
    metrics = [_component(1, name="Conversion Rate", data_type="integer")]
    findings = check_type_name_mismatch(_impl(metrics=metrics), _ctx("SCH-004", severity="low"))
    assert len(findings) == 1
    assert findings[0].id == "SCH-004"


def test_type_name_mismatch_quiet_when_decimal_or_unrelated_name():
    metrics = [
        _component(1, name="Conversion Rate", data_type="decimal"),
        _component(2, name="Page Views", data_type="integer"),
    ]
    findings = check_type_name_mismatch(_impl(metrics=metrics), _ctx("SCH-004", severity="low"))
    assert findings == []


# ---------------------------------------------------------------------------
# SCH-005 deprecated components
# ---------------------------------------------------------------------------


def test_deprecated_quiet_when_no_deprecated_markers():
    metrics = [_component(1, name="Active Metric", tags=["custom"])]
    calc = [_calc("calc/use_active", refs=[metrics[0].id])]
    findings = check_deprecated_components(_impl(metrics=metrics, calc=calc), _ctx("SCH-005", severity="low"))
    assert findings == []


def test_deprecated_fires_when_marker_and_referenced():
    metrics = [_component(1, name="Old Page Views", tags=["deprecated"])]
    calc = [_calc("calc/still_using", refs=[metrics[0].id])]
    findings = check_deprecated_components(_impl(metrics=metrics, calc=calc), _ctx("SCH-005", severity="low"))
    assert len(findings) == 1


def test_deprecated_quiet_when_marker_but_no_consumers():
    metrics = [_component(1, name="Old Page Views", tags=["deprecated"])]
    findings = check_deprecated_components(_impl(metrics=metrics), _ctx("SCH-005", severity="low"))
    assert findings == []


# ---------------------------------------------------------------------------
# SCH-006 cardinality (stub)
# ---------------------------------------------------------------------------


def test_cardinality_concerns_is_no_op_in_v0_1():
    findings = check_cardinality_concerns(_impl(), _ctx("SCH-006"))
    assert findings == []

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
    check_derived_field_broken_refs,
    check_derived_field_cycles,
    check_duplicate_component_names,
    check_persistence_lookback_cap,
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


def test_type_name_mismatch_fires_on_aa_counter_event_with_rate_name():
    """AA event type `counter` stores integers — a rate-named counter event
    is the exact silent-truncation bug SCH-004 was designed to catch, but
    the original integer-type set didn't recognize AA's vocabulary."""
    metrics = [_component(1, name="Conversion Rate", data_type="counter")]
    findings = check_type_name_mismatch(_impl(metrics=metrics), _ctx("SCH-004", severity="low"))
    assert len(findings) == 1
    assert findings[0].id == "SCH-004"


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


def test_deprecated_quiet_when_name_contains_innocuous_substring():
    """Per RUBRIC_AUDIT.md, the original regex matched `old`, `tmp`, `temp`,
    and `v0` — which false-fired on legitimate names like "Order Total",
    "temperature", and "eVar0". The narrowed default regex excludes those.
    A component with one of these innocuous substrings AND no deprecation
    tag must not be flagged."""
    metrics = [
        _component(1, name="Order Total", cid="metrics/order_total"),
        _component(2, name="temperature", cid="metrics/temperature"),
        _component(3, name="Custom Var 0", cid="variables/evar0"),
    ]
    # Make them referenced so they'd fire if the regex still matched.
    calc = [_calc("calc/uses_them", refs=[m.id for m in metrics])]
    findings = check_deprecated_components(
        _impl(metrics=metrics, calc=calc), _ctx("SCH-005", severity="low")
    )
    assert findings == []


def test_deprecated_still_fires_on_explicit_legacy_marker_in_name():
    """The narrowed regex still catches the explicit cases — `deprecated`,
    `legacy`, `deleteme`, `do_not_use` — even when no tag is set."""
    metrics = [
        _component(1, name="Legacy Conversion Rate", cid="metrics/legacy_conv"),
    ]
    calc = [_calc("calc/still_using", refs=[metrics[0].id])]
    findings = check_deprecated_components(
        _impl(metrics=metrics, calc=calc), _ctx("SCH-005", severity="low")
    )
    assert len(findings) == 1


def test_deprecated_fires_on_old_marker_in_name():
    """`\\bold\\b` re-added in PR 4 after the May 2026 corpus vetting:
    the narrowing applied in 1c2abf3 lost 3 genuine `(old)` deprecation
    flags across the 108-fixture private corpus (`Account Name (old)`,
    `Old Order Status`, `Old Page Type`). The abstract false-positive
    risks (`Holdovers`, `Order Total`) can't match `\\bold\\b` due to
    word-boundary semantics, so re-adding it is net positive."""
    metrics = [
        _component(1, name="Account Name (old)", cid="metrics/account_name_old"),
    ]
    calc = [_calc("calc/still_using", refs=[metrics[0].id])]
    findings = check_deprecated_components(
        _impl(metrics=metrics, calc=calc), _ctx("SCH-005", severity="low")
    )
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# SCH-006 cardinality (stub)
# ---------------------------------------------------------------------------


def test_cardinality_concerns_is_no_op_in_v0_1():
    findings = check_cardinality_concerns(_impl(), _ctx("SCH-006"))
    assert findings == []


# ---------------------------------------------------------------------------
# SCH-007 CJA persistence lookback cap
# ---------------------------------------------------------------------------


def _dim_with_persistence(idx: int, persistence: Any, *, name: str | None = None) -> Component:
    dim = Component(
        id=f"variables/dim_{idx:03d}",
        name=name or f"Dim {idx:03d}",
        description=None,
        component_type="dimension",
        data_type="string",
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=None,
        tags=[],
        platform_specific={"persistenceSetting": persistence},
    )
    return dim


def test_persistence_cap_no_op_on_aa():
    """SCH-007 is CJA-only — must skip AA snapshots even if data is present."""
    aa_impl = Implementation(
        platform="aa", instance_id="rs_x", instance_name="x",
        snapshot_taken_at=None, snapshot_source="t", adapter_version="0",
        metrics=[], dimensions=[_dim_with_persistence(1, '{"enabled":true,"lookback":{"granularity":"day","numPeriods":180}}')],
        segments=[], calculated_metrics=[], derived_fields=[], raw={},
    )
    assert check_persistence_lookback_cap(aa_impl, _ctx("SCH-007")) == []


def test_persistence_cap_quiet_when_disabled():
    impl = _impl(dimensions=[_dim_with_persistence(1, '{"enabled":false}')])
    assert check_persistence_lookback_cap(impl, _ctx("SCH-007")) == []


def test_persistence_cap_quiet_when_within_cap():
    """30-day inactivity expiration is well within Adobe's 90-day cap."""
    setting = (
        '{"enabled":true,"allocationModel":{"func":"allocation-lastTouch_dim",'
        '"expiration":{"func":"allocation-inactivity","granularity":"day","numPeriods":30}}}'
    )
    impl = _impl(dimensions=[_dim_with_persistence(1, setting)])
    assert check_persistence_lookback_cap(impl, _ctx("SCH-007")) == []


def test_persistence_cap_fires_when_days_exceed_cap():
    setting = (
        '{"enabled":true,"allocationModel":{"func":"allocation-lastTouch_dim",'
        '"expiration":{"func":"allocation-inactivity","granularity":"day","numPeriods":120}}}'
    )
    impl = _impl(dimensions=[_dim_with_persistence(1, setting, name="Campaign")])
    findings = check_persistence_lookback_cap(impl, _ctx("SCH-007"))
    assert len(findings) == 1
    assert "lookback=120 days" in str(findings[0].body)


def test_persistence_cap_translates_months_to_days():
    """4 months of granularity = 120 days, which exceeds the 90-day cap."""
    setting = (
        '{"enabled":true,"lookback":{"func":"min-months",'
        '"granularity":"month","numPeriods":4}}'
    )
    impl = _impl(dimensions=[_dim_with_persistence(1, setting)])
    findings = check_persistence_lookback_cap(impl, _ctx("SCH-007"))
    assert len(findings) == 1


def test_persistence_cap_handles_nan_sentinel():
    """cja_auto_sdr emits float('nan') for missing settings — must skip cleanly."""
    impl = _impl(dimensions=[_dim_with_persistence(1, float("nan"))])
    assert check_persistence_lookback_cap(impl, _ctx("SCH-007")) == []


def test_persistence_cap_handles_malformed_json():
    impl = _impl(dimensions=[_dim_with_persistence(1, "not-json {")])
    assert check_persistence_lookback_cap(impl, _ctx("SCH-007")) == []


def test_persistence_cap_skips_container_expirations():
    """Container-scoped expirations (sessions/visitors) carry no day count
    — the rule cannot evaluate them and must skip rather than fire."""
    setting = (
        '{"enabled":true,"allocationModel":{"func":"allocation-lastTouch_dim",'
        '"expiration":{"func":"allocation-container","context":"sessions"}}}'
    )
    impl = _impl(dimensions=[_dim_with_persistence(1, setting)])
    assert check_persistence_lookback_cap(impl, _ctx("SCH-007")) == []


# ---------------------------------------------------------------------------
# SCH-008 derived-field cycles (CJA-only)
# ---------------------------------------------------------------------------


def _derived(cid: str, *, refs: list[str] | None = None,
             lookup_refs: list[str] | None = None) -> Component:
    return Component(
        id=cid,
        name=cid,
        description=None,
        component_type="derived_field",
        data_type="string",
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=None,
        tags=[],
        platform_specific={
            "component_references": refs or [],
            "lookup_references": lookup_refs or [],
        },
    )


def test_derived_field_cycles_quiet_when_no_chains():
    derived = [
        _derived("variables/df_a", refs=["web.webPageDetails.URL"]),
        _derived("variables/df_b", refs=[]),
    ]
    impl = _impl(derived=derived)
    assert check_derived_field_cycles(impl, _ctx("SCH-008")) == []


def test_derived_field_cycles_quiet_on_aa():
    """AA fixtures don't have derived fields; the check must short-circuit."""
    impl = Implementation(
        platform="aa",
        instance_id="rs",
        instance_name="rs",
        snapshot_taken_at=None,
        snapshot_source="t",
        adapter_version="0",
        metrics=[],
        dimensions=[],
        segments=[],
        calculated_metrics=[],
        derived_fields=[_derived("variables/df_a", refs=["variables/df_a"])],
        raw={},
    )
    assert check_derived_field_cycles(impl, _ctx("SCH-008")) == []


def test_derived_field_cycles_fires_on_self_loop():
    derived = [_derived("variables/df_a", refs=["variables/df_a"])]
    findings = check_derived_field_cycles(_impl(derived=derived), _ctx("SCH-008"))
    assert len(findings) == 1
    assert findings[0].id == "SCH-008"
    assert "1 derived-field reference cycle" in findings[0].title


def test_derived_field_cycles_fires_on_two_node_cycle():
    derived = [
        _derived("variables/df_a", refs=["variables/df_b"]),
        _derived("variables/df_b", refs=["variables/df_a"]),
    ]
    findings = check_derived_field_cycles(_impl(derived=derived), _ctx("SCH-008"))
    assert len(findings) == 1
    assert "1 derived-field reference cycle" in findings[0].title


def test_derived_field_cycles_fires_on_three_node_cycle():
    derived = [
        _derived("variables/a", refs=["variables/b"]),
        _derived("variables/b", refs=["variables/c"]),
        _derived("variables/c", refs=["variables/a"]),
    ]
    findings = check_derived_field_cycles(_impl(derived=derived), _ctx("SCH-008"))
    assert len(findings) == 1


def test_derived_field_cycles_dedups_rotations():
    """A -> B -> A and B -> A -> B are the same cycle; only one finding."""
    derived = [
        _derived("variables/a", refs=["variables/b"]),
        _derived("variables/b", refs=["variables/a"]),
    ]
    findings = check_derived_field_cycles(_impl(derived=derived), _ctx("SCH-008"))
    assert "1 derived-field reference cycle" in findings[0].title


def test_derived_field_cycles_normalizes_namespace_prefix():
    """`dimensions/X` references must resolve to `variables/X` definitions."""
    derived = [
        _derived("variables/a", refs=["dimensions/b"]),
        _derived("variables/b", refs=["variables/a"]),
    ]
    findings = check_derived_field_cycles(_impl(derived=derived), _ctx("SCH-008"))
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# SCH-009 derived-field broken refs (CJA-only)
# ---------------------------------------------------------------------------


def test_derived_field_broken_refs_quiet_when_all_resolve():
    metrics = [_component(1, cid="metrics/orders")]
    derived = [_derived("variables/df_a", refs=["metrics/orders"])]
    impl = _impl(metrics=metrics, derived=derived)
    assert check_derived_field_broken_refs(impl, _ctx("SCH-009")) == []


def test_derived_field_broken_refs_fires_on_missing_target():
    derived = [_derived("variables/df_a", refs=["metrics/m_deleted"])]
    findings = check_derived_field_broken_refs(_impl(derived=derived), _ctx("SCH-009"))
    assert len(findings) == 1
    assert findings[0].id == "SCH-009"
    assert "1 broken derived-field reference" in findings[0].title


def test_derived_field_broken_refs_filters_platform_builtins():
    """CJA built-ins like `metrics/adobe_sessionends` are valid even when
    not enumerated in the snapshot's metrics/dimensions blocks."""
    derived = [_derived("variables/df_a", refs=[
        "metrics/adobe_sessionends",
        "dimensions/daterangemonth",
        "dimensions/timepartmonthofyear",
        "dimensions/platformdatasetid",
    ])]
    findings = check_derived_field_broken_refs(_impl(derived=derived), _ctx("SCH-009"))
    assert findings == []


def test_derived_field_broken_refs_normalizes_namespace_prefix():
    """`dimensions/X` references must resolve against `variables/X` definitions —
    CJA SDR stores dimensions under `variables/` but refs use `dimensions/`."""
    dimensions = [_component(1, cid="variables/sd_ajo_messageProfileId",
                             comp_type="dimension", data_type="string")]
    derived = [_derived("variables/df_a", refs=["dimensions/sd_ajo_messageProfileId"])]
    impl = _impl(dimensions=dimensions, derived=derived)
    assert check_derived_field_broken_refs(impl, _ctx("SCH-009")) == []


def test_derived_field_broken_refs_quiet_on_aa():
    impl = Implementation(
        platform="aa",
        instance_id="rs",
        instance_name="rs",
        snapshot_taken_at=None,
        snapshot_source="t",
        adapter_version="0",
        metrics=[],
        dimensions=[],
        segments=[],
        calculated_metrics=[],
        derived_fields=[_derived("variables/df_a", refs=["metrics/totally_missing"])],
        raw={},
    )
    assert check_derived_field_broken_refs(impl, _ctx("SCH-009")) == []


def test_derived_field_broken_refs_truncates_to_show_top():
    derived = [
        _derived(f"variables/df_{i}", refs=[f"metrics/missing_{i}"])
        for i in range(15)
    ]
    findings = check_derived_field_broken_refs(
        _impl(derived=derived), _ctx("SCH-009", show_top=5),
    )
    assert "showing first 5 of 15" in findings[0].title

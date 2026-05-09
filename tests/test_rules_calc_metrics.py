"""Tests for calc_metric_maint rules (CALC-*)."""

from __future__ import annotations

from _rule_test_helpers import calc, component, ctx, impl, segment
from sdr_grader.rules.checks.calc_metrics import (
    check_attribution_model_variety,
    check_calc_complexity_threshold,
    check_calc_deprecated_allocations,
    check_calc_formula_broken_refs,
    check_calc_identical_formula_text,
    check_calc_metrics_missing_descriptions,
    check_calc_near_duplicates,
    check_orphan_calc_metrics,
)


# CALC-001
def test_calc_missing_descriptions_fires():
    cms = [calc(f"c{i}", description=None) for i in range(3)]
    cms += [calc(f"c{i + 3}", description="ok") for i in range(2)]  # 60% missing
    findings = check_calc_metrics_missing_descriptions(
        impl(calc=cms), ctx("CALC-001", category="calc_metric_maint", threshold=0.20),
    )
    assert len(findings) == 1


def test_calc_missing_descriptions_quiet_under_threshold():
    cms = [calc(f"c{i}", description="ok") for i in range(9)]
    cms += [calc("c_bad", description=None)]
    findings = check_calc_metrics_missing_descriptions(
        impl(calc=cms), ctx("CALC-001", category="calc_metric_maint", threshold=0.20),
    )
    assert findings == []


# CALC-002
def test_calc_formula_broken_refs_fires():
    metrics = [component(1, cid="metrics/visits")]
    cms = [calc("c", references=["metrics/visits", "metrics/missing"])]
    findings = check_calc_formula_broken_refs(
        impl(metrics=metrics, calc=cms),
        ctx("CALC-002", category="calc_metric_maint"),
    )
    assert len(findings) == 1
    assert "1 broken" in findings[0].title


def test_calc_formula_broken_refs_quiet_when_resolved():
    metrics = [
        component(1, cid="metrics/visits"),
        component(2, cid="metrics/orders"),
    ]
    cms = [calc("c", references=["metrics/visits", "metrics/orders"])]
    findings = check_calc_formula_broken_refs(
        impl(metrics=metrics, calc=cms),
        ctx("CALC-002", category="calc_metric_maint"),
    )
    assert findings == []


# CALC-003
def test_calc_complexity_fires_above_threshold():
    cms = [calc("c1", complexity_score=80.0), calc("c2", complexity_score=20.0)]
    findings = check_calc_complexity_threshold(
        impl(calc=cms), ctx("CALC-003", category="calc_metric_maint", max_complexity=75.0),
    )
    assert len(findings) == 1


# CALC-004
def test_attribution_variety_fires_above_distinct_cap():
    cms = [
        calc("a", attribution_model="last-touch"),
        calc("b", attribution_model="first-touch"),
        calc("c", attribution_model="linear"),
        calc("d", attribution_model="u-shaped"),
        calc("e", attribution_model="time-decay"),
    ]
    findings = check_attribution_model_variety(
        impl(calc=cms), ctx("CALC-004", category="calc_metric_maint", max_distinct=4),
    )
    assert len(findings) == 1


def test_attribution_variety_quiet_when_within_cap():
    cms = [
        calc("a", attribution_model="last-touch"),
        calc("b", attribution_model="linear"),
    ]
    findings = check_attribution_model_variety(
        impl(calc=cms), ctx("CALC-004", category="calc_metric_maint", max_distinct=4),
    )
    assert findings == []


# CALC-005
def test_orphan_calc_metrics_fires_when_unreferenced():
    cms = [calc(f"c{i}") for i in range(5)]
    findings = check_orphan_calc_metrics(
        impl(calc=cms), ctx("CALC-005", category="calc_metric_maint", threshold=0.50),
    )
    assert len(findings) == 1


def test_orphan_calc_metrics_quiet_when_referenced_enough():
    cms = [calc(f"c{i}") for i in range(5)]
    referencing = [segment("segments/s", references=[c.id for c in cms[:3]])]
    findings = check_orphan_calc_metrics(
        impl(calc=cms, segments=referencing),
        ctx("CALC-005", category="calc_metric_maint", threshold=0.50),
    )
    assert findings == []


# CALC-014
def test_near_duplicates_fires_on_shared_reference_set():
    refs = ["metrics/revenue", "metrics/visits"]
    cms = [
        calc("a", references=list(refs)),
        calc("b", references=list(refs)),
        calc("c", references=["metrics/orders", "metrics/visits"]),
    ]
    findings = check_calc_near_duplicates(
        impl(calc=cms), ctx("CALC-014", category="calc_metric_maint", min_similarity=0.85),
    )
    assert len(findings) == 1


# CALC-015
def test_identical_formula_text_fires():
    cms = [
        calc("a", formula_text="Revenue / Visits"),
        calc("b", formula_text="Revenue / Visits"),
        calc("c", formula_text="Orders / Visits"),
    ]
    findings = check_calc_identical_formula_text(
        impl(calc=cms), ctx("CALC-015", category="calc_metric_maint"),
    )
    assert len(findings) == 1


def test_identical_formula_text_quiet_when_unique():
    cms = [
        calc("a", formula_text="Revenue / Visits"),
        calc("b", formula_text="Orders / Visits"),
    ]
    findings = check_calc_identical_formula_text(
        impl(calc=cms), ctx("CALC-015", category="calc_metric_maint"),
    )
    assert findings == []


# CALC-022
def test_deprecated_allocations_fires_on_match():
    cms = [calc("a", allocation="linear-deprecated"), calc("b", allocation="most-recent")]
    findings = check_calc_deprecated_allocations(
        impl(calc=cms), ctx("CALC-022", category="calc_metric_maint"),
    )
    assert len(findings) == 1


def test_deprecated_allocations_quiet_otherwise():
    cms = [calc("a", allocation="most-recent")]
    findings = check_calc_deprecated_allocations(
        impl(calc=cms), ctx("CALC-022", category="calc_metric_maint"),
    )
    assert findings == []

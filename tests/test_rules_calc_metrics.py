"""Tests for calc_metric_maint rules (CALC-*)."""

from __future__ import annotations

from _rule_test_helpers import calc, component, ctx, impl, segment
from sdr_grader.rules.checks.calc_metrics import (
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
        impl(calc=cms),
        ctx("CALC-001", category="calc_metric_maint", threshold=0.20),
    )
    assert len(findings) == 1


def test_calc_missing_descriptions_quiet_under_threshold():
    cms = [calc(f"c{i}", description="ok") for i in range(9)]
    cms += [calc("c_bad", description=None)]
    findings = check_calc_metrics_missing_descriptions(
        impl(calc=cms),
        ctx("CALC-001", category="calc_metric_maint", threshold=0.20),
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
        impl(calc=cms),
        ctx("CALC-003", category="calc_metric_maint", max_complexity=75.0),
    )
    assert len(findings) == 1


# CALC-005
def test_orphan_calc_metrics_fires_when_unreferenced():
    cms = [calc(f"c{i}") for i in range(5)]
    findings = check_orphan_calc_metrics(
        impl(calc=cms),
        ctx("CALC-005", category="calc_metric_maint", threshold=0.50),
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


def test_orphan_calc_metrics_quiet_when_empty_or_all_referenced():
    context = ctx("CALC-005", category="calc_metric_maint", threshold=0.50)
    assert check_orphan_calc_metrics(impl(), context) == []

    cms = [calc("c1"), calc("c2")]
    referencing = [segment("segments/s", references=[cm.id for cm in cms])]
    assert (
        check_orphan_calc_metrics(
            impl(calc=cms, segments=referencing),
            context,
        )
        == []
    )


# CALC-014
def test_near_duplicates_fires_on_shared_reference_set():
    refs = ["metrics/revenue", "metrics/visits"]
    cms = [
        calc("a", references=list(refs)),
        calc("b", references=list(refs)),
        calc("c", references=["metrics/orders", "metrics/visits"]),
    ]
    findings = check_calc_near_duplicates(
        impl(calc=cms),
        ctx("CALC-014", category="calc_metric_maint", min_similarity=0.85),
    )
    assert len(findings) == 1


def test_near_duplicates_fires_on_approximate_reference_overlap():
    cms = [
        calc("a", references=["metrics/a", "metrics/b", "metrics/c"]),
        calc("b", references=["metrics/a", "metrics/b", "metrics/d"]),
    ]
    findings = check_calc_near_duplicates(
        impl(calc=cms),
        ctx("CALC-014", category="calc_metric_maint", min_similarity=0.50),
    )
    assert len(findings) == 1
    assert "a, b" in findings[0].body[1].items[0]


def test_near_duplicates_quiet_when_reference_sets_do_not_overlap_enough():
    cms = [
        calc("a", references=["metrics/a", "metrics/b"]),
        calc("b", references=["metrics/c", "metrics/d"]),
    ]
    findings = check_calc_near_duplicates(
        impl(calc=cms),
        ctx("CALC-014", category="calc_metric_maint", min_similarity=0.85),
    )
    assert findings == []


def test_near_duplicates_deduplicates_repeated_component_ids():
    cms = [
        calc("duplicate", references=["metrics/a", "metrics/b"]),
        calc("duplicate", references=["metrics/a", "metrics/b"]),
        calc("duplicate", references=["metrics/a", "metrics/b", "metrics/c"]),
    ]
    findings = check_calc_near_duplicates(
        impl(calc=cms),
        ctx("CALC-014", category="calc_metric_maint", min_similarity=0.60),
    )
    assert len(findings) == 1
    assert findings[0].body[1].items == ["duplicate"]


# CALC-015
def test_identical_formula_text_fires():
    cms = [
        calc("a", formula_text="Revenue / Visits"),
        calc("b", formula_text="Revenue / Visits"),
        calc("c", formula_text="Orders / Visits"),
    ]
    findings = check_calc_identical_formula_text(
        impl(calc=cms),
        ctx("CALC-015", category="calc_metric_maint"),
    )
    assert len(findings) == 1


def test_identical_formula_text_quiet_when_unique():
    cms = [
        calc("a", formula_text="Revenue / Visits"),
        calc("b", formula_text="Orders / Visits"),
    ]
    findings = check_calc_identical_formula_text(
        impl(calc=cms),
        ctx("CALC-015", category="calc_metric_maint"),
    )
    assert findings == []


def test_identical_formula_text_ignores_empty_formulas():
    cms = [calc("empty", formula_text=""), calc("unique", formula_text="x / y")]
    findings = check_calc_identical_formula_text(
        impl(calc=cms),
        ctx("CALC-015", category="calc_metric_maint"),
    )
    assert findings == []


# CALC-022
def test_deprecated_allocations_fires_on_match():
    cms = [calc("a", allocation="linear-deprecated"), calc("b", allocation="most-recent")]
    findings = check_calc_deprecated_allocations(
        impl(calc=cms),
        ctx("CALC-022", category="calc_metric_maint"),
    )
    assert len(findings) == 1


def test_deprecated_allocations_quiet_otherwise():
    cms = [calc("a", allocation="most-recent")]
    findings = check_calc_deprecated_allocations(
        impl(calc=cms),
        ctx("CALC-022", category="calc_metric_maint"),
    )
    assert findings == []

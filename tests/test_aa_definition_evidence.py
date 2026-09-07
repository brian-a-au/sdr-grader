"""Public API AST examples distinguish references from literal values.

Sources:
https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/segments/definition
https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/calculatedmetrics/
"""

import json

import pytest

from sdr_grader.adapters.aa import adapt
from sdr_grader.rules.checks.calc_metrics import (
    check_calc_formula_broken_refs,
    check_calc_identical_formula_text,
)
from sdr_grader.rules.checks.schema_hygiene import check_broken_references
from sdr_grader.rules.engine import RuleContext


def _snapshot(**sections):
    return {"report_suite": {"rsid": "synthetic"}, "dimensions": [], "metrics": [], **sections}


def _ctx(rule_id):
    return RuleContext(rule_id, "Reference evidence", "high", "schema_hygiene", ["aa"])


def _segment(predicate):
    return {
        "id": "s_synthetic",
        "definition": {
            "func": "segment",
            "version": [1, 0, 0],
            "container": {"func": "container", "context": "hits", "pred": predicate},
        },
    }


@pytest.mark.parametrize(
    ("func", "key", "literal"),
    [
        ("streq", "str", "metrics/documentation"),
        ("streq-in", "list", ["segments/documentation", "variables/example"]),
        ("matches", "glob", "calculatedMetrics/example*"),
    ],
)
@pytest.mark.parametrize("present", [True, False])
def test_segment_literals_are_not_refs_but_missing_attribute_is_detected(
    func, key, literal, present
):
    predicate = {
        "func": func,
        "val": {"func": "attr", "name": "variables/page"},
        key: literal,
        "description": "metrics/a-description",
    }
    normalized = adapt(
        _snapshot(
            dimensions=[{"id": "variables/page"}] if present else [],
            segments=[_segment(predicate)],
        )
    )
    assert normalized.segments[0].references == ["variables/page"]
    assert bool(check_broken_references(normalized, _ctx("SCH-002"))) is not present


@pytest.mark.parametrize("present", [True, False])
def test_segment_typed_event_is_a_reference(present):
    normalized = adapt(
        _snapshot(
            metrics=[{"id": "metrics/revenue"}] if present else [],
            segments=[
                _segment(
                    {
                        "func": "gt",
                        "num": 0,
                        "val": {
                            "func": "total",
                            "evt": {"func": "event", "name": "metrics/revenue"},
                        },
                    }
                )
            ],
        )
    )
    assert normalized.segments[0].references == ["metrics/revenue"]
    assert bool(check_broken_references(normalized, _ctx("SCH-002"))) is not present


def _formula(numerator):
    return {
        "func": "visualization-group",
        "col": {
            "func": "divide",
            "col1": {"func": "metric", "name": numerator},
            "col2": {"func": "metric", "name": "metrics/visitors"},
        },
    }


@pytest.mark.parametrize("present", [True, False])
def test_calculated_metric_named_operands_resolve_or_report_missing(present):
    formula = _formula("metrics/revenue")
    normalized = adapt(
        _snapshot(
            metrics=[{"id": "metrics/visitors"}] + ([{"id": "metrics/revenue"}] if present else []),
            calculated_metrics=[{"id": "cm_synthetic", "definition": {"formula": formula}}],
        )
    )
    metric = normalized.calculated_metrics[0]
    assert metric.references == ["metrics/revenue", "metrics/visitors"]
    assert json.loads(metric.formula_text) == formula
    assert bool(check_calc_formula_broken_refs(normalized, _ctx("CALC-002"))) is not present
    assert bool(check_broken_references(normalized, _ctx("SCH-002"))) is not present


@pytest.mark.parametrize("same", [True, False])
def test_distinct_official_formulas_are_not_duplicates_but_equal_formulas_are(same):
    normalized = adapt(
        _snapshot(
            calculated_metrics=[
                {"id": "cm_a", "definition": {"formula": _formula("metrics/revenue")}},
                {
                    "id": "cm_b",
                    "definition": {
                        "formula": _formula("metrics/revenue" if same else "metrics/orders")
                    },
                },
            ]
        )
    )
    assert bool(check_calc_identical_formula_text(normalized, _ctx("CALC-015"))) is same
    assert (
        normalized.calculated_metrics[0].formula_text
        == normalized.calculated_metrics[1].formula_text
    ) is same


@pytest.mark.parametrize("present", [True, False])
def test_saved_segment_filter_uses_exact_id_without_prefix_rewrite(present):
    # API-client source: adobeanalyticsr R/cm_function.R constructs
    # filters=[{func: segment-ref, id: <saved ID>, description: ...}].
    normalized = adapt(
        _snapshot(
            metrics=[{"id": "metrics/revenue"}],
            segments=[
                _segment({"func": "exists", "val": {"func": "attr", "name": "variables/page"}})
            ]
            if present
            else [],
            calculated_metrics=[
                {
                    "id": "cm_synthetic",
                    "definition": {
                        "func": "calc-metric",
                        "formula": {"func": "metric", "name": "metrics/revenue"},
                        "filters": [
                            {
                                "func": "segment-ref",
                                "id": "s_synthetic",
                                "description": "metrics/label",
                            }
                        ],
                    },
                }
            ],
        )
    )
    assert normalized.calculated_metrics[0].references == ["metrics/revenue", "s_synthetic"]
    assert bool(check_calc_formula_broken_refs(normalized, _ctx("CALC-002"))) is not present


@pytest.mark.parametrize("same", [True, False])
def test_outer_saved_segment_filters_remain_part_of_formula_evidence(same):
    definitions = [
        {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {"func": "metric", "name": "metrics/revenue"},
            "filters": [{"func": "segment-ref", "id": saved_segment}],
        }
        for saved_segment in ["s_a", "s_a" if same else "s_b"]
    ]
    normalized = adapt(
        _snapshot(
            calculated_metrics=[
                {"id": f"cm_{index}", "definition": definition}
                for index, definition in enumerate(definitions)
            ]
        )
    )
    for metric, definition in zip(normalized.calculated_metrics, definitions, strict=True):
        assert metric.formula == definition
        assert json.loads(metric.formula_text) == definition
    assert bool(check_calc_identical_formula_text(normalized, _ctx("CALC-015"))) is same

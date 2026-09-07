"""Regressions for CJA API IDs omitted from, or aliased in, SDR exports."""

from pathlib import Path

import pytest

from _rule_test_helpers import ctx
from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt
from sdr_grader.core.grader import grade
from sdr_grader.render import render
from sdr_grader.rules.checks.calc_metrics import check_calc_formula_broken_refs
from sdr_grader.rules.checks.schema_hygiene import (
    check_broken_references,
    check_derived_field_broken_refs,
)
from sdr_grader.rules.rubric import load_rubric

CORE_METRICS = ["metrics/occurrences", "metrics/visits", "metrics/visitors"]
CHECKS = [
    (check_broken_references, "SCH-002"),
    (check_calc_formula_broken_refs, "CALC-002"),
    (check_derived_field_broken_refs, "SCH-009"),
]


def snapshot(refs, dimensions=None, metrics=None):
    return {
        "metadata": {"Data View ID": "dv_test"},
        "metrics": metrics or [],
        "dimensions": dimensions or [],
        "segments": [{"id": "s1", "metric_references": refs}],
        "calculated_metrics": [{"id": "c1", "metric_references": refs}],
        "derived_fields": [{"id": "df1", "component_references": refs}],
    }


@pytest.mark.parametrize("check,rule_id", CHECKS)
def test_core_metrics_resolve_without_inventory_rows(check, rule_id):
    implementation = adapt(snapshot(CORE_METRICS))
    assert check(implementation, ctx(rule_id)) == []
    assert implementation.metrics == []  # No fabricated inventory for other rules.
    assert implementation.calculated_metrics[0].references == CORE_METRICS
    assert implementation.segments[0].references == CORE_METRICS


@pytest.mark.parametrize("stored,referenced", [
    ("variables/channel", "dimensions/channel"),
    ("dimensions/channel", "variables/channel"),
])
@pytest.mark.parametrize("check,rule_id", CHECKS)
def test_dimension_aliases_resolve(check, rule_id, stored, referenced):
    implementation = adapt(snapshot([referenced], [{"id": stored}]))
    assert check(implementation, ctx(rule_id)) == []
    assert implementation.dimensions[0].id == stored


@pytest.mark.parametrize("check,rule_id", CHECKS[:2])
def test_aliases_do_not_hide_missing_ids_or_metric_dimension_collisions(check, rule_id):
    refs = ["dimensions/channel", "metrics/deleted", "segments/absent", "metrics/visits_custom"]
    implementation = adapt(snapshot(refs, metrics=[{"id": "metrics/channel"}]))
    findings = check(implementation, ctx(rule_id))
    evidence = " ".join(item for block in findings[0].body for item in (block.items or []))
    assert all(ref in evidence for ref in refs)
    assert "does not prove the live implementation is broken" in findings[0].body[0].html


@pytest.mark.parametrize("check,rule_id", CHECKS[:2])
def test_aa_does_not_inherit_cja_resolution(check, rule_id):
    implementation = adapt_aa({
        "report_suite": {"rsid": "test"}, "metrics": [], "dimensions": [],
        "calculated_metrics": [{"id": "c1", "definition": {"formula": {"args": CORE_METRICS}}}],
    })
    assert implementation.available_reference_ids == set()
    assert check(implementation, ctx(rule_id))


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_html_does_not_report_legacy_core_metric_ids_as_broken(pack):
    implementation = adapt(snapshot([*CORE_METRICS, "metrics/deleted"]))
    rubric = load_rubric(Path(__file__).parents[1] / "src/sdr_grader/rules/packs" / pack)
    report = grade(implementation, rubric)
    html = render(report)
    assert all(metric not in html for metric in CORE_METRICS)
    assert "metrics/deleted" in html
    assert "does not prove the live implementation is broken" in html
    assert html == render(grade(implementation, rubric))


@pytest.mark.parametrize("check,rule_id", CHECKS)
def test_core_metric_names_do_not_resolve_missing_dimensions(check, rule_id):
    refs = ["dimensions/visits", "dimensions/visitors", "dimensions/occurrences"]
    implementation = adapt(snapshot([*CORE_METRICS, *refs]))
    findings = check(implementation, ctx(rule_id))
    evidence = " ".join(item for block in findings[0].body for item in (block.items or []))
    assert all(ref in evidence for ref in refs)
    assert all(ref not in evidence for ref in CORE_METRICS)

"""Shared defensive coercion mirrored with sdr-visualizer: limits and string-only values."""

from __future__ import annotations

import json

import pytest

from sdr_grader.adapters import aa, cja
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.structure_limits import MAX_DEFINITION_NODES, MAX_STRUCTURE_DEPTH


def _cja(**updates):
    snapshot = {"metadata": {"Data View ID": "dv_test"}, "metrics": [], "dimensions": []}
    snapshot.update(updates)
    return snapshot


def _aa(**updates):
    snapshot = {"report_suite": {"rsid": "test"}, "dimensions": [], "metrics": []}
    snapshot.update(updates)
    return snapshot


def _nested_list(depth):
    value: list = []
    for _ in range(depth):
        value = [value]
    return value


OVER_DEPTH = _nested_list(MAX_STRUCTURE_DEPTH + 5)
OVER_NODES = list(range(MAX_DEFINITION_NODES + 5))


@pytest.mark.parametrize("decoded", [OVER_DEPTH, OVER_NODES], ids=["depth", "nodes"])
def test_cja_decoded_non_object_definition_respects_limits(decoded):
    with pytest.raises(InvalidSnapshotError, match="definition"):
        cja._parse_definition_json(json.dumps(decoded), label="definition")


def test_cja_decoded_small_non_object_definition_still_degrades():
    assert cja._parse_definition_json("[1, 2]") == {}
    assert cja._parse_definition_json('"text"') == {}


def test_cja_oversized_list_definition_rejected_through_adapter():
    snapshot = _cja(
        calculated_metrics=[{"metric_id": "cm", "definition_json": json.dumps(OVER_NODES)}]
    )
    with pytest.raises(InvalidSnapshotError):
        cja.adapt(snapshot)


def test_aa_calc_metric_definition_without_formula_respects_limits():
    snapshot = _aa(calculated_metrics=[{"id": "cm", "definition": {"extra": OVER_NODES}}])
    with pytest.raises(InvalidSnapshotError, match="calculated metric definition"):
        aa.adapt(snapshot)


def test_aa_calc_metric_formula_limit_label_is_unchanged():
    formula = {"func": "add", "args": OVER_NODES}
    snapshot = _aa(calculated_metrics=[{"id": "cm", "definition": {"formula": formula}}])
    with pytest.raises(InvalidSnapshotError, match="calculated metric formula"):
        aa.adapt(snapshot)


@pytest.mark.parametrize(
    "definition", [[OVER_NODES], [{"func": "container", "context": "hits"}], "text", 7]
)
def test_aa_non_object_segment_definition_is_empty_and_not_walked(definition):
    snapshot = _aa(segments=[{"id": "s", "definition": definition}])
    segment = aa.adapt(snapshot).segments[0]
    assert segment.definition == {}
    assert segment.nesting_depth == 0
    assert segment.container_types == []
    assert segment.references == []


@pytest.mark.parametrize(
    "value",
    [
        ["metrics/a", None, {"x": 1}, 3, True, "", "  ", ["metrics/b"], "metrics/c"],
        json.dumps(["metrics/a", None, {"x": 1}, 3, True, "", "  ", ["metrics/b"], "metrics/c"]),
    ],
    ids=["native", "encoded"],
)
def test_cja_reference_list_keeps_only_non_empty_strings(value):
    assert cja._parse_ref_list(value) == ["metrics/a", "metrics/c"]


@pytest.mark.parametrize("bad", [{"func": "lookback"}, ["x"], 7, True])
def test_cja_non_string_attribution_and_allocation_are_omitted(bad):
    assert cja._extract_attribution({"attribution": bad, "allocation": bad}) == (None, None)
    assert cja._extract_attribution({"func": {"model": bad, "allocation": bad}}) == (None, None)


def test_cja_string_attribution_falls_through_non_string_top_level():
    formula = {"attribution": {"x": 1}, "func": {"model": "linear", "allocation": "recent"}}
    assert cja._extract_attribution(formula) == ("linear", "recent")


@pytest.mark.parametrize("bad", [{"x": 1}, ["summary"], 7, True])
def test_cja_non_string_formula_summary_is_empty(bad):
    impl = cja.adapt(_cja(calculated_metrics=[{"metric_id": "cm", "formula_summary": bad}]))
    assert impl.calculated_metrics[0].formula_text == ""


def test_cja_formula_summary_falls_through_to_definition_summary():
    record = {"metric_id": "cm", "formula_summary": ["x"], "definition_summary": "a / b"}
    impl = cja.adapt(_cja(calculated_metrics=[record]))
    assert impl.calculated_metrics[0].formula_text == "a / b"


@pytest.mark.parametrize("bad", [{"x": 1}, ["event"], 7, True])
def test_cja_non_string_contexts_never_become_container_types(bad):
    definition = {"func": "container", "context": bad, "pred": {"func": "container"}}
    record = {"segment_id": "s", "definition_json": definition, "container_type": bad}
    impl = cja.adapt(_cja(segments=[record]))
    assert impl.segments[0].container_types == []


def test_cja_declared_string_container_type_still_falls_back():
    record = {"segment_id": "s", "definition_json": {}, "container_type": "visit"}
    impl = cja.adapt(_cja(segments=[record]))
    assert impl.segments[0].container_types == ["visit"]

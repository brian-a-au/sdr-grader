"""Definition classification is companion metadata, never canonical extraction."""

import pytest

from sdr_grader.adapters.aa import _calc_from_record
from sdr_grader.adapters.cja import _calc_metric_from_record


def metric(platform, definition, **record):
    if platform == "aa":
        return _calc_from_record({"id": "cm", "definition": definition, **record})
    return _calc_metric_from_record({"id": "cm", "definition_json": definition, **record})


def eligible(cm, ref):
    classification = cm.reference_classifications.get(ref)
    return (
        classification is not None
        and classification.kinds == {"segment"}
        and not classification.blockers
    )


@pytest.mark.parametrize("platform", ["aa", "cja"])
def test_typed_children_and_conflicting_kinds_preserve_canonical_references(platform):
    definition = {
        "func": "unknown",
        "formula": {
            "func": "add",
            "args": [
                {"func": "segment-ref", "id": "s"},
                {"func": "metric", "name": "m"},
                {"func": "attr", "name": "d"},
                {"func": "segment-ref", "id": "m"},
            ],
        },
    }
    cm = metric(platform, definition)
    assert cm.references == (["s", "m", "d"] if platform == "aa" else ["d", "m", "s"])
    assert eligible(cm, "s")
    assert cm.reference_classifications["m"].kinds == {"metric", "segment"}
    assert not eligible(cm, "m")
    assert not eligible(cm, "d")


def test_aa_outer_definition_and_untyped_operand():
    cm = metric("aa", {"filter": {"func": "segment-ref", "id": "segments/s"}})
    assert cm.formula == {}
    assert cm.references == ["segments/s"]
    assert eligible(cm, "segments/s")
    cm = metric("aa", {"args": ["segments/s", {"func": "segment-ref", "id": "segments/s"}]})
    assert cm.references == ["segments/s"]
    assert not eligible(cm, "segments/s")


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("key", ["str", "list", "glob", "description", "name", "extension"])
def test_literal_and_extension_nodes_do_not_type(platform, key):
    cm = metric(platform, {key: {"func": "segment-ref", "id": "s"}})
    assert not eligible(cm, "s")


@pytest.mark.parametrize(
    "wrapper, expected",
    [
        ({"id": "s", "name": "Label"}, True),
        ([None, "", {"id": "s"}, "s"], True),
        ({"segment_id": "s", "id": "other"}, False),
        (["s", "other"], False),
        ({"name": "s", "metric": "other"}, False),
        ({"id": "s", "segment_id": 12}, False),
    ],
)
def test_cja_wrapper_identity_ambiguity_does_not_change_first_selection(wrapper, expected):
    cm = metric("cja", {"func": "segment", "segment_id": wrapper})
    assert cm.references == ["s"]
    assert eligible(cm, "s") == expected


def test_cja_summary_does_not_override_definition_or_type_independent_summary():
    cm = metric(
        "cja",
        {"func": "segment-ref", "id": "segments/s"},
        metric_references=["segments/s"],
        segment_references=["s", "only_summary"],
    )
    assert cm.references == ["only_summary", "segments/s"]
    assert eligible(cm, "segments/s")
    assert not eligible(cm, "only_summary")


@pytest.mark.parametrize("definition", [None, "not JSON", {}, {"func": "unknown", "id": "s"}])
def test_missing_unknown_definitions_remain_unknown(definition):
    cm = metric("cja", definition, segment_references=["s"])
    assert cm.references == ["s"]
    assert not eligible(cm, "s")


def test_malformed_cja_slot_blocks_only_affected_sibling():
    cm = metric(
        "cja",
        {
            "args": [
                {"func": "segment-ref", "segment_id": "s", "id": ["s"]},
                {"func": "segment-ref", "id": "good"},
            ]
        },
    )
    assert cm.references == ["good", "s"]
    assert not eligible(cm, "s")
    assert eligible(cm, "good")


@pytest.mark.parametrize("platform", ["aa", "cja"])
def test_malformed_nonsegment_identity_prevents_flattened_segment_exemption(platform):
    cm = metric(
        platform,
        {
            "args": [
                {"func": "segment-ref", "id": "s"},
                {"func": "metric", "name": ["s"]},
                {"func": "segment-ref", "id": "good"},
            ]
        },
    )
    assert not eligible(cm, "s")
    assert eligible(cm, "good")


@pytest.mark.parametrize(
    "platform,slot",
    [("aa", "id"), ("aa", "name"), ("cja", "id"), ("cja", "segment_id"), ("cja", "name")],
)
@pytest.mark.parametrize("identity", ["s", ["s"], {"id": "s"}])
def test_unknown_identity_occurrence_blocks_same_id_only(platform, slot, identity):
    cm = metric(
        platform,
        {
            "args": [
                {"func": "segment-ref", "id": "s"},
                {"func": "unsupported", slot: identity},
                {"func": "segment-ref", "id": "good"},
            ]
        },
    )
    assert not eligible(cm, "s")
    assert eligible(cm, "good")
    assert cm.references == (["s", "good"] if platform == "aa" else ["good", "s"])

    from _rule_test_helpers import impl
    from sdr_grader.core.reference_policy import POLICY_PARAM, REFERENCE_CHECKS, assess_references

    for check_name in REFERENCE_CHECKS:
        assessment = assess_references(
            impl(platform=platform, calc=[cm]),
            check_name=check_name,
            params={POLICY_PARAM: True},
        )
        assert [ref.target_id for ref in assessment.unresolved_scoring] == ["s"]
        assert [ref.target_id for ref in assessment.excluded] == ["good"]
        assert not assessment.not_assessed


def test_legacy_normalized_metric_defaults_to_no_classification():
    from sdr_grader.core.models import CalculatedMetric

    cm = CalculatedMetric("cm", "CM", None, {}, "", None, None, 0, ["s"])
    assert cm.reference_classifications == {}

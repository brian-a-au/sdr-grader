"""AA adapter tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdr_grader.adapters.aa import adapt
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.grader import grade
from sdr_grader.input.detect import detect_platform
from sdr_grader.rules.rubric import load_rubric

FIXTURES = Path(__file__).parent / "fixtures"
STRICT_PACK = (
    Path(__file__).resolve().parent.parent / "src" / "sdr_grader" / "rules" / "packs" / "strict"
)


@pytest.fixture(scope="module")
def messy_aa():
    return json.loads((FIXTURES / "aa_snapshot_messy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clean_aa():
    return json.loads((FIXTURES / "aa_snapshot_clean.json").read_text(encoding="utf-8"))


def test_detect_recognizes_aa_snapshot(messy_aa):
    assert detect_platform(messy_aa) == "aa"


def test_detect_recognizes_cja_snapshot():
    cja = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    assert detect_platform(cja) == "cja"


def test_aa_adapter_basic_shape(messy_aa):
    impl = adapt(messy_aa)
    assert impl.platform == "aa"
    assert impl.instance_id == "messy.prod"
    assert impl.instance_name == "Messy Production"
    assert impl.adapter_version == "1.0.0"
    assert impl.derived_fields == []  # CJA-only concept


def test_aa_adapter_combines_evars_and_props_into_dimensions(messy_aa):
    impl = adapt(messy_aa)
    evars = [d for d in impl.dimensions if d.id.startswith("variables/evar")]
    props = [d for d in impl.dimensions if d.id.startswith("variables/prop")]
    assert len(evars) == 40
    assert len(props) == 20
    # eVars carry their AA-specific allocation in platform_specific.extra.
    sample = next(d for d in evars if d.id == "variables/evar2")
    assert sample.platform_specific.get("extra", {}).get("allocation") == "most-recent"


def test_aa_adapter_lifts_classifications_to_tags(messy_aa):
    impl = adapt(messy_aa)
    evar1 = next(d for d in impl.dimensions if d.id == "variables/evar1")
    assert "Campaign Metadata" in evar1.tags


def test_aa_adapter_calc_metric_references(messy_aa):
    impl = adapt(messy_aa)
    cm = next(c for c in impl.calculated_metrics if c.id == "cm_conversion_rate")
    assert cm.references == ["metrics/orders", "metrics/visits"]
    assert cm.formula_text.startswith("divide(")


def test_aa_adapter_segment_nesting_depth_and_contexts(messy_aa):
    impl = adapt(messy_aa)
    nested = next(s for s in impl.segments if s.id == "s_returning")
    # Definition has a "visitors" container wrapping an `and` predicate whose
    # two args are sibling "visits" and "hits" containers (not stacked inside
    # each other) — 3 distinct contexts, but only 2 levels of container
    # nesting: visitors -> {visits, hits}.
    assert set(nested.container_types) == {"visitors", "visits", "hits"}
    assert nested.nesting_depth >= 2


def test_aa_adapter_dash_descriptions_normalize_to_none():
    snapshot = {
        "report_suite": {"rsid": "test"},
        "dimensions": [{"id": "variables/evar1", "name": "X", "description": "-"}],
        "metrics": [],
    }
    impl = adapt(snapshot)
    assert impl.dimensions[0].description is None


def test_aa_adapter_rejects_snapshot_without_report_suite():
    with pytest.raises(InvalidSnapshotError, match="report_suite"):
        adapt({"dimensions": [], "metrics": []})


def test_aa_adapter_rejects_snapshot_without_rsid():
    with pytest.raises(InvalidSnapshotError, match="rsid"):
        adapt({"report_suite": {}, "dimensions": [], "metrics": []})


def test_aa_clean_grades_better_than_aa_messy(messy_aa, clean_aa):
    rubric = load_rubric(STRICT_PACK)
    messy_pct = grade(adapt(messy_aa), rubric).overall_pct
    clean_pct = grade(adapt(clean_aa), rubric).overall_pct
    assert clean_pct > messy_pct


def test_missing_dimensions_key_raises():
    snap = {"report_suite": {"rsid": "rs1"}, "metrics": []}
    with pytest.raises(InvalidSnapshotError, match="dimensions"):
        adapt(snap)


def test_stringified_tags_parse_as_list():
    from sdr_grader.adapters.aa import _component_from_record

    comp = _component_from_record({"id": "evar1", "tags": '["marketing", "web"]'}, "dimension", {})
    assert comp.tags == ["marketing", "web"]


def test_non_iterable_tags_become_empty():
    from sdr_grader.adapters.aa import _component_from_record

    comp = _component_from_record({"id": "evar1", "tags": 7}, "dimension", {})
    assert comp.tags == []


def test_non_numeric_complexity_defaults_to_zero():
    from sdr_grader.adapters.aa import _calc_from_record

    calc = _calc_from_record({"id": "cm1", "complexity_score": "N/A"})
    assert calc.complexity_score == 0.0


def test_single_container_segment_depth_is_one():
    from sdr_grader.adapters.aa import _walk_segment_definition

    definition = {
        "func": "segment",
        "version": [1, 0, 0],
        "container": {
            "func": "container",
            "context": "visits",
            "pred": {
                "func": "streq",
                "str": "Home",
                "val": {"func": "attr", "name": "variables/page"},
            },
        },
    }
    depth, contexts = _walk_segment_definition(definition)
    assert depth == 1
    assert contexts == ["visits"]


def test_nested_containers_count_only_containers():
    from sdr_grader.adapters.aa import _walk_segment_definition

    inner = {
        "func": "container",
        "context": "hits",
        "pred": {"func": "exists", "val": {"func": "attr", "name": "variables/evar1"}},
    }
    outer = {"func": "container", "context": "visits", "pred": {"func": "without", "arg": inner}}
    depth, contexts = _walk_segment_definition({"func": "segment", "container": outer})
    assert depth == 2
    assert contexts == ["visits", "hits"]


@pytest.mark.parametrize("key", ["calculated_metrics", "segments"])
@pytest.mark.parametrize("bad_value", [7, "not-a-list", {"id": "x"}, True])
def test_non_list_optional_sections_raise(key, bad_value):
    """A present-but-non-list calculated_metrics/segments value is a malformed
    export, not an empty one — reject it instead of crashing (fuzz regression:
    replace_truthy_int on the top-level key hit a bare TypeError)."""
    snap = {"report_suite": {"rsid": "rs1"}, "dimensions": [], "metrics": [], key: bad_value}
    with pytest.raises(InvalidSnapshotError, match=key):
        adapt(snap)


@pytest.mark.parametrize("key", ["calculated_metrics", "segments"])
def test_null_or_missing_optional_sections_stay_empty(key):
    missing = {"report_suite": {"rsid": "rs1"}, "dimensions": [], "metrics": []}
    null = {**missing, key: None}
    for snap in (missing, null):
        impl = adapt(snap)
        assert getattr(impl, key) == []


def test_formula_text_renders_nested_formulas_readably():
    snapshot = {
        "report_suite": {"rsid": "test"},
        "dimensions": [],
        "metrics": [],
        "calculated_metrics": [
            {
                "id": "cm_nested",
                "name": "Nested",
                "definition": {
                    "formula": {
                        "func": "divide",
                        "args": [
                            {"func": "add", "args": ["metrics/orders", "metrics/units"]},
                            "metrics/visits",
                        ],
                    }
                },
            }
        ],
    }
    impl = adapt(snapshot)
    cm = impl.calculated_metrics[0]
    assert cm.formula_text == "divide(add(metrics/orders, metrics/units), metrics/visits)"
    assert "{" not in cm.formula_text  # no Python repr leaking to users


# ---------------------------------------------------------------------------
# Wrong-typed optional timestamps (visualizer parity): a non-string
# created/modified is missing, not a value worth fabricating. Owner needs no
# equivalent guard — its owner_id path is already cast. Mirrored from
# sdr-visualizer (SPEC §11/§15).
# ---------------------------------------------------------------------------


def test_component_non_string_timestamps_become_none():
    from sdr_grader.adapters.aa import _component_from_record

    comp = _component_from_record(
        {"id": "evar1", "created": 1735689600, "modified": 1735776000}, "dimension", {}
    )
    assert comp.created_at is None
    assert comp.modified_at is None


def test_calc_metric_non_string_timestamps_become_none():
    from sdr_grader.adapters.aa import _calc_from_record

    calc = _calc_from_record({"id": "cm1", "created": 1735689600, "modified": 1735776000})
    assert calc.created_at is None
    assert calc.modified_at is None


def test_segment_non_string_timestamps_become_none():
    from sdr_grader.adapters.aa import _segment_from_record

    seg = _segment_from_record({"id": "s1", "created": 1735689600, "modified": 1735776000})
    assert seg.created_at is None
    assert seg.modified_at is None


def test_classification_without_name_or_id_is_skipped():
    from sdr_grader.adapters.aa import _index_classifications

    idx = _index_classifications(
        [
            {"parent": "variables/evar1"},
            {"parent": "variables/evar1", "name": "Campaign"},
        ]
    )
    assert idx == {"variables/evar1": ["Campaign"]}


# ---------------------------------------------------------------------------
# Q5 (1.0.0): generator-version compatibility warning helper. Warn-only,
# never refuse. Mirrors the sdr-visualizer originals (SPEC §11/§15).
# ---------------------------------------------------------------------------


def test_newer_generator_version_warns():
    from sdr_grader.adapters.aa import (
        TESTED_THROUGH_GENERATOR_VERSION,
        generator_version_warning,
    )

    msg = generator_version_warning("99.0.0")
    assert msg is not None
    assert TESTED_THROUGH_GENERATOR_VERSION in msg
    assert "99.0.0" in msg


def test_equal_older_or_unparseable_versions_do_not_warn():
    from sdr_grader.adapters.aa import (
        TESTED_THROUGH_GENERATOR_VERSION,
        generator_version_warning,
    )

    assert generator_version_warning(TESTED_THROUGH_GENERATOR_VERSION) is None
    assert generator_version_warning("0.0.1") is None
    assert generator_version_warning("unknown") is None
    assert generator_version_warning("") is None
    assert generator_version_warning("3.5.x") is None


def test_tuple_length_mismatch_versions_compare_correctly():
    from sdr_grader.adapters.aa import generator_version_warning

    assert generator_version_warning("1.19") is not None
    assert generator_version_warning("1.18") is None


# ---------------------------------------------------------------------------
# Deterministic normalization and validation characterization
# ---------------------------------------------------------------------------


def _minimal_snapshot(**overrides):
    snapshot = {
        "report_suite": {"rsid": "rs1", "name": "Main suite"},
        "dimensions": [],
        "metrics": [],
    }
    snapshot.update(overrides)
    return snapshot


def test_report_suite_alias_and_snapshot_metadata_normalize():
    impl = adapt(
        {
            "reportSuite": {"RSID": "rs-alias", "name": "Alias suite"},
            "dimensions": [],
            "metrics": [],
            "captured": " 2026-07-18T12:00:00Z ",
            "tool_version": 7,
        },
        source="alias.json",
    )

    assert impl.instance_id == "rs-alias"
    assert impl.instance_name == "Alias suite"
    assert impl.snapshot_taken_at == "2026-07-18T12:00:00Z"
    assert impl.adapter_version == "7"
    assert impl.snapshot_source == "alias.json"


def test_aa_rejects_non_object_top_level_and_report_suite():
    with pytest.raises(InvalidSnapshotError, match="top-level JSON object, got list"):
        adapt([])  # type: ignore[arg-type]

    with pytest.raises(InvalidSnapshotError, match="report_suite.*object.*str"):
        adapt(_minimal_snapshot(report_suite="rs1"))


@pytest.mark.parametrize("key", ["dimensions", "metrics"])
def test_required_collections_reject_wrong_types(key):
    with pytest.raises(InvalidSnapshotError, match=rf"'{key}'.*list.*dict"):
        adapt(_minimal_snapshot(**{key: {}}))


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (7, "expected dimension record to be an object, got int"),
        ({"name": "No ID"}, "dimension record is missing 'id'"),
    ],
)
def test_dimension_records_reject_invalid_shapes(record, message):
    with pytest.raises(InvalidSnapshotError, match=message):
        adapt(_minimal_snapshot(dimensions=[record]))


def test_classification_index_skips_invalid_entries_and_uses_id_fallback():
    from sdr_grader.adapters.aa import _index_classifications

    assert _index_classifications("not-a-list") == {}
    assert _index_classifications(
        [
            "not-an-object",
            {"name": "No parent"},
            {"parent": "variables/evar1", "id": "classifications/region"},
        ]
    ) == {"variables/evar1": ["classifications/region"]}


def test_formula_helpers_characterize_empty_scalar_and_recursive_shapes():
    from sdr_grader.adapters.aa import (
        _extract_aa_calc_refs,
        _stringify_formula,
    )

    assert _stringify_formula({}) == ""
    assert _stringify_formula({"func": "sum", "args": "metrics/orders"}) == ("sum(metrics/orders)")
    # Strings buried in an arbitrary nested list are walked but are not
    # promoted to references; only direct formula args carry reference meaning.
    assert _extract_aa_calc_refs(
        {
            "func": "add",
            "args": [
                ["metrics/orders", "variables/evar1", "not-a-reference"],
                {"func": "segment", "args": ["segments/buyers"]},
                "metrics/orders",
            ],
        }
    ) == ["segments/buyers", "metrics/orders"]


@pytest.mark.parametrize(
    ("section", "record", "message"),
    [
        ("calculated_metrics", 7, "expected calculated metric to be an object"),
        ("calculated_metrics", {"name": "No ID"}, "calc metric missing 'id'"),
        ("segments", 7, "expected segment to be an object"),
        ("segments", {"name": "No ID"}, "segment missing 'id'"),
    ],
)
def test_optional_component_records_reject_invalid_shapes(section, record, message):
    with pytest.raises(InvalidSnapshotError, match=message):
        adapt(_minimal_snapshot(**{section: [record]}))


def test_governance_component_fields_and_malformed_tags_preserve_contract():
    snapshot = _minimal_snapshot(
        dimensions=[
            {
                "id": "variables/evar1",
                "description": 7,
                "polarity": " Positive ",
                "tags": "not-json",
                "owner_id": 42,
                "allocation": "most-recent",
            }
        ],
        metrics=[{"id": "metrics/orders", "polarity": "upward"}],
        calculated_metrics=[
            {
                "id": "cm1",
                "extra": {
                    "publishingStatus": {"published": False},
                    "shares": ["group-a", "group-b"],
                },
            }
        ],
        segments=[
            {
                "id": "s1",
                "extra": {
                    "publishingStatus": {"published": True},
                    "shares": [],
                },
            }
        ],
    )

    impl = adapt(snapshot)
    dimension = impl.dimensions[0]
    assert dimension.description is None
    assert dimension.polarity == "positive"
    assert dimension.tags == []
    assert dimension.owner == "42"
    assert dimension.platform_specific["allocation"] == "most-recent"
    assert impl.metrics[0].polarity is None
    assert (impl.calculated_metrics[0].approved, impl.calculated_metrics[0].shared_to_count) == (
        False,
        2,
    )
    assert (impl.segments[0].approved, impl.segments[0].shared_to_count) == (True, 0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, 0.0), (3, 3.0), (float("inf"), 0.0), (" 2.5 ", 2.5)],
)
def test_numeric_coercion_accepts_only_finite_non_boolean_values(value, expected):
    from sdr_grader.adapters.aa import _safe_float

    assert _safe_float(value) == expected


def test_cja_snapshot_forced_through_aa_keeps_platform_validation_failure():
    cja = json.loads((FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8"))

    with pytest.raises(InvalidSnapshotError, match="not an AA snapshot"):
        adapt(cja)

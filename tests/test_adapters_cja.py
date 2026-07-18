"""CJA adapter tests.

Per SPEC §8 Phase 2: round-trip every field, segment depth and calc metric
complexity computed correctly, references extracted. The messy fixture
encodes specific known counts (487 components, 220 missing descriptions,
4 deep segments, 7 near-duplicate revenue calc metrics) — those numbers
are part of the test contract and downstream rule tests rely on them.
Counts were retuned post-calibration so the messy fixture exercises the
calibrated SCH-003 strict threshold (0.35); see docs/threshold_calibration.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdr_grader.adapters.cja import adapt
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.models import CalculatedMetric, Component, Implementation, Segment

FIXTURES = Path(__file__).parent / "fixtures"
MESSY_PATH = FIXTURES / "cja_snapshot_messy.json"
CLEAN_PATH = FIXTURES / "cja_snapshot_clean.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def messy_snapshot() -> dict:
    return json.loads(MESSY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clean_snapshot() -> dict:
    return json.loads(CLEAN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def messy_impl(messy_snapshot) -> Implementation:
    return adapt(messy_snapshot, source=str(MESSY_PATH))


@pytest.fixture(scope="module")
def clean_impl(clean_snapshot) -> Implementation:
    return adapt(clean_snapshot, source=str(CLEAN_PATH))


# ---------------------------------------------------------------------------
# Top-level Implementation shape
# ---------------------------------------------------------------------------


def test_messy_implementation_metadata(messy_impl: Implementation) -> None:
    assert messy_impl.platform == "cja"
    assert messy_impl.instance_id == "dv_messy_prod_web"
    assert messy_impl.instance_name == "Production Web Analytics"
    assert messy_impl.adapter_version == "3.5.17"
    assert messy_impl.snapshot_source.endswith("cja_snapshot_messy.json")
    assert messy_impl.snapshot_taken_at == "2026-04-25 09:14:00"
    assert isinstance(messy_impl.raw, dict) and "metadata" in messy_impl.raw


def test_messy_total_components_is_487(messy_impl: Implementation) -> None:
    assert len(messy_impl.metrics) == 142
    assert len(messy_impl.dimensions) == 203
    assert len(messy_impl.derived_fields) == 142
    total = len(messy_impl.metrics) + len(messy_impl.dimensions) + len(messy_impl.derived_fields)
    assert total == 487


def test_messy_missing_descriptions_total_220(messy_impl: Implementation) -> None:
    """Adapter must surface missing descriptions; cja_auto_sdr writes '-' for them."""
    components = [*messy_impl.metrics, *messy_impl.dimensions, *messy_impl.derived_fields]
    missing = [c for c in components if c.description is None]
    assert len(missing) == 220
    metrics_missing = sum(1 for c in messy_impl.metrics if c.description is None)
    dims_missing = sum(1 for c in messy_impl.dimensions if c.description is None)
    derived_missing = sum(1 for c in messy_impl.derived_fields if c.description is None)
    assert metrics_missing == 70
    assert dims_missing == 100
    assert derived_missing == 50


# ---------------------------------------------------------------------------
# Component round-trip
# ---------------------------------------------------------------------------


def test_metric_record_round_trips(messy_impl: Implementation) -> None:
    """Spot-check both the integer and currency code paths.

    Builder rule: idx %% 3 == 0 -> currency/decimal, else int/integer.
    """
    int_metric = next(m for m in messy_impl.metrics if m.id == "metrics/cm_metric_001")
    assert isinstance(int_metric, Component)
    assert int_metric.component_type == "metric"
    assert int_metric.name == "Metric 001"
    assert int_metric.description is None
    assert int_metric.data_type == "integer"
    assert int_metric.created_at == "2025-09-01T00:00:00Z"
    assert int_metric.modified_at == "2025-09-01T00:00:00Z"
    assert int_metric.owner.endswith("@example.com")
    assert int_metric.platform_specific.get("precision") == 0

    currency_metric = next(m for m in messy_impl.metrics if m.id == "metrics/cm_metric_003")
    assert currency_metric.data_type == "decimal"
    assert currency_metric.platform_specific.get("precision") == 2


def test_dimension_record_round_trips(messy_impl: Implementation) -> None:
    dim = next(d for d in messy_impl.dimensions if d.id == "variables/evar1")
    assert dim.component_type == "dimension"
    assert dim.name == "Dimension 001"
    assert dim.description is None
    assert dim.data_type == "string"


def test_derived_field_round_trips(messy_impl: Implementation) -> None:
    # First 50 derived fields are missing descriptions; df_field_051 is the
    # first that should carry one. Use it for the round-trip check.
    derived = next(d for d in messy_impl.derived_fields if d.id == "derived/df_field_051")
    assert derived.component_type == "derived_field"
    assert derived.name == "Derived Field 051"
    assert derived.description == "Auto-generated derived field 051."
    assert derived.platform_specific.get("schema_field_count") == 2


def test_components_with_descriptions_keep_them(messy_impl: Implementation) -> None:
    documented = next(m for m in messy_impl.metrics if m.id == "metrics/cm_metric_071")
    assert documented.description == "Auto-generated metric 071."


def test_dash_descriptions_normalize_to_none(messy_impl: Implementation) -> None:
    """cja_auto_sdr emits '-' for missing descriptions; adapter must coerce to None."""
    no_desc_metric = next(m for m in messy_impl.metrics if m.description is None)
    raw = next(m for m in messy_impl.raw["metrics"] if m["id"] == no_desc_metric.id)
    assert raw["description"] == "-"


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


def test_messy_has_25_segments_with_4_deep(messy_impl: Implementation) -> None:
    assert len(messy_impl.segments) == 25
    deep = [s for s in messy_impl.segments if s.nesting_depth >= 5]
    depths = sorted([s.nesting_depth for s in deep], reverse=True)
    assert depths == [8, 6, 6, 5]


def test_segment_container_types_extracted_from_definition(messy_impl: Implementation) -> None:
    """Adapter walks definition_json for distinct container contexts."""
    seg = next(s for s in messy_impl.segments if s.id == "segments/seg_qualified_lead_v3")
    assert isinstance(seg, Segment)
    # Three distinct contexts present in the nested definition.
    assert set(seg.container_types) == {"event", "session", "person"}
    assert seg.nesting_depth == 8


def test_segment_references_combined_from_three_lists(messy_impl: Implementation) -> None:
    seg = next(s for s in messy_impl.segments if s.id == "segments/seg_qualified_lead_v3")
    # Adapter merges dimension_references + metric_references + other_segment_references.
    assert "variables/evar1" in seg.references
    assert "metrics/cm_metric_001" in seg.references


def test_shallow_segment_falls_back_to_declared_container_when_no_nested(messy_impl: Implementation) -> None:
    # The shallow segments do contain a container in their definition; this also
    # exercises that the walk finds it correctly.
    seg = next(s for s in messy_impl.segments if s.id == "segments/seg_simple_001")
    assert seg.container_types == ["event"]
    assert seg.nesting_depth == 2


# ---------------------------------------------------------------------------
# Calculated metrics
# ---------------------------------------------------------------------------


def test_messy_has_30_calc_metrics(messy_impl: Implementation) -> None:
    assert len(messy_impl.calculated_metrics) == 30


def test_seven_near_duplicate_revenue_calc_metrics(messy_impl: Implementation) -> None:
    near_dups = [
        cm for cm in messy_impl.calculated_metrics
        if cm.formula_text == "Revenue / Visits"
    ]
    assert len(near_dups) == 7
    assert all(set(cm.references) == {"metrics/revenue", "metrics/visits"} for cm in near_dups)


def test_calc_metric_round_trip(messy_impl: Implementation) -> None:
    cm = next(c for c in messy_impl.calculated_metrics if c.id == "calculatedMetrics/cm_revenue_per_visit")
    assert isinstance(cm, CalculatedMetric)
    assert cm.complexity_score == 42.0
    assert cm.formula_text == "Revenue / Visits"
    assert cm.references == ["metrics/revenue", "metrics/visits"]
    assert cm.formula["func"] == "divide"  # parsed from definition_json string
    assert cm.owner == "r.kim@example.com"


def test_calc_metric_distinct_complexity_preserved(messy_impl: Implementation) -> None:
    distinct = next(c for c in messy_impl.calculated_metrics if c.id == "calculatedMetrics/cm_orders_per_visit")
    assert distinct.complexity_score == 25.0
    assert distinct.formula_text == "Orders / Visits"


# ---------------------------------------------------------------------------
# Clean snapshot
# ---------------------------------------------------------------------------


def test_clean_implementation_basic_shape(clean_impl: Implementation) -> None:
    assert clean_impl.platform == "cja"
    assert clean_impl.instance_id == "dv_clean_prod_web"
    assert len(clean_impl.metrics) == 12
    assert len(clean_impl.dimensions) == 18
    assert len(clean_impl.derived_fields) == 10
    assert len(clean_impl.segments) == 8
    assert len(clean_impl.calculated_metrics) == 5


def test_clean_snapshot_has_no_missing_descriptions(clean_impl: Implementation) -> None:
    components = [*clean_impl.metrics, *clean_impl.dimensions, *clean_impl.derived_fields]
    assert all(c.description is not None for c in components)
    assert all(s.description is not None for s in clean_impl.segments)
    assert all(cm.description is not None for cm in clean_impl.calculated_metrics)


def test_clean_segments_are_shallow(clean_impl: Implementation) -> None:
    assert all(s.nesting_depth <= 2 for s in clean_impl.segments)


def test_clean_calc_metrics_are_distinct(clean_impl: Implementation) -> None:
    formula_summaries = [cm.formula_text for cm in clean_impl.calculated_metrics]
    assert len(set(formula_summaries)) == len(formula_summaries)


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_adapt_rejects_non_dict() -> None:
    with pytest.raises(InvalidSnapshotError, match="top-level JSON object"):
        adapt(["not a dict"])  # type: ignore[arg-type]


def test_adapt_rejects_snapshot_missing_metadata() -> None:
    with pytest.raises(InvalidSnapshotError, match="metadata"):
        adapt({"metrics": [], "dimensions": []})


def test_adapt_rejects_snapshot_without_data_view_id() -> None:
    with pytest.raises(InvalidSnapshotError, match="Data View ID"):
        adapt({"metadata": {"Tool Version": "1"}, "metrics": [], "dimensions": []})


def test_adapt_rejects_non_list_metrics() -> None:
    with pytest.raises(InvalidSnapshotError, match="metrics"):
        adapt({
            "metadata": {"Data View ID": "dv_x"},
            "metrics": {"not": "a list"},
            "dimensions": [],
        })


# ---------------------------------------------------------------------------
# Field-shape tolerance — cja_auto_sdr ships some list/dict fields as
# JSON-encoded strings. The adapter must round-trip those into real lists.
# ---------------------------------------------------------------------------


def _minimal_snapshot(*, dim_tags, metric_tags=None):
    return {
        "metadata": {"Data View ID": "dv_x"},
        "metrics": [{"id": "metrics/m1", "name": "M1", "tags": metric_tags or []}],
        "dimensions": [{"id": "variables/d1", "name": "D1", "tags": dim_tags}],
    }


def test_string_encoded_tags_parsed_as_list() -> None:
    """cja_auto_sdr ships `tags` as a JSON-encoded string like `'["custom"]'`.

    The adapter previously called `list(record.get("tags") or [])` which
    iterates the raw string as characters, producing tags like `'['`,
    `'"'`, `'c'`. Verify the JSON-string form parses back to a real list.
    """
    impl = adapt(_minimal_snapshot(dim_tags='["custom","ga4"]'))
    dim = impl.dimensions[0]
    assert dim.tags == ["custom", "ga4"]


def test_empty_string_tags_parsed_as_empty_list() -> None:
    impl = adapt(_minimal_snapshot(dim_tags="[]"))
    dim = impl.dimensions[0]
    assert dim.tags == []


def test_native_list_tags_still_accepted() -> None:
    impl = adapt(_minimal_snapshot(dim_tags=["custom"]))
    dim = impl.dimensions[0]
    assert dim.tags == ["custom"]


def test_malformed_tag_string_falls_back_to_empty() -> None:
    """A non-parsable JSON string should not crash — fall back to empty list."""
    impl = adapt(_minimal_snapshot(dim_tags="not-json-{["))
    dim = impl.dimensions[0]
    assert dim.tags == []


def test_stringified_reference_lists_parse():
    from sdr_grader.adapters.cja import _calc_metric_from_record

    calc = _calc_metric_from_record(
        {"metric_id": "cm1", "metric_references": '["metrics/a"]'}
    )
    assert calc.references == ["metrics/a"]


def test_wrong_typed_references_and_numerics_degrade():
    from sdr_grader.adapters.cja import _calc_metric_from_record, _segment_from_record

    calc = _calc_metric_from_record(
        {"metric_id": "cm1", "metric_references": 7, "complexity_score": "N/A"}
    )
    assert calc.references == []
    assert calc.complexity_score == 0.0

    seg = _segment_from_record({"segment_id": "s1", "nesting_depth": "deep"})
    assert seg.nesting_depth == 0


def test_numeric_inline_echo_of_derived_field_is_deduped():
    snap = {
        "metadata": {"Data View ID": "dv1"},
        "metrics": [],
        "dimensions": [{"id": 123, "name": "My DF"}],
        "derived_fields": {"fields": [{"component_id": 123, "component_name": "My DF"}]},
    }
    impl = adapt(snap)
    assert [d.id for d in impl.dimensions] == []
    assert [df.id for df in impl.derived_fields] == ["123"]


# ---------------------------------------------------------------------------
# Q5 (1.0.0): generator-version compatibility warning helper. Warn-only,
# never refuse. Mirrored to sdr-grader (SPEC §11/§15).
# ---------------------------------------------------------------------------


def test_newer_generator_version_warns():
    from sdr_grader.adapters.cja import (
        TESTED_THROUGH_GENERATOR_VERSION,
        generator_version_warning,
    )

    msg = generator_version_warning("99.0.0")
    assert msg is not None
    assert TESTED_THROUGH_GENERATOR_VERSION in msg
    assert "99.0.0" in msg


def test_equal_older_or_unparseable_versions_do_not_warn():
    from sdr_grader.adapters.cja import (
        TESTED_THROUGH_GENERATOR_VERSION,
        generator_version_warning,
    )

    assert generator_version_warning(TESTED_THROUGH_GENERATOR_VERSION) is None
    assert generator_version_warning("0.0.1") is None
    assert generator_version_warning("unknown") is None
    assert generator_version_warning("") is None
    assert generator_version_warning("3.5.x") is None

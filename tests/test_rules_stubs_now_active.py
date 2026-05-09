"""Tests for rules that were previously no-op stubs and now read from
supplementary_data: GOV-006 (doc_drift), SCH-006 (cardinality_concerns),
AAEVAR-001 (eVar distinct values), CJASTITCH-001 (unstitched IDs).
"""

from __future__ import annotations

from _rule_test_helpers import component, ctx, impl
from sdr_grader.rules.checks.governance import check_doc_drift
from sdr_grader.rules.checks.platform_specific import (
    check_aa_evar_distinct_values,
    check_cja_stitching_unstitched,
)
from sdr_grader.rules.checks.schema_hygiene import check_cardinality_concerns

# ---------------------------------------------------------------------------
# GOV-006 doc_drift
# ---------------------------------------------------------------------------


def _modified(idx: int, when: str, *, comp_type: str = "metric") -> object:
    c = component(idx, comp_type=comp_type)
    c.modified_at = when  # mutable dataclass — bypass frozen
    return c


def test_doc_drift_no_op_without_signal():
    metrics = [_modified(i, "2026-01-01T00:00:00Z") for i in range(5)]
    findings = check_doc_drift(
        impl(metrics=metrics), ctx("GOV-006", category="governance_posture"),
    )
    assert findings == []


def test_doc_drift_fires_when_modifications_exceed_threshold():
    metrics = [_modified(i, "2026-03-01T00:00:00Z") for i in range(8)]
    metrics += [_modified(i + 8, "2025-06-01T00:00:00Z") for i in range(2)]
    findings = check_doc_drift(
        impl(metrics=metrics),
        ctx(
            "GOV-006",
            category="governance_posture",
            threshold=0.20,
            last_sdr_update_at="2026-01-15",
        ),
    )
    assert len(findings) == 1
    assert "8 of 10 components" in findings[0].body[0].html


def test_doc_drift_reads_from_supplementary_sdr():
    metrics = [_modified(i, "2026-03-01T00:00:00Z") for i in range(5)]
    findings = check_doc_drift(
        impl(
            metrics=metrics,
            raw={"metadata": {}},
        ).__class__(
            **{**impl(metrics=metrics).__dict__,
               "supplementary_data": {"sdr": {"last_updated_at": "2026-01-15"}}},
        ),
        ctx("GOV-006", category="governance_posture", threshold=0.20),
    )
    assert len(findings) == 1


def test_doc_drift_quiet_when_under_threshold():
    metrics = [_modified(i, "2026-01-01T00:00:00Z") for i in range(9)]
    metrics += [_modified(99, "2026-03-01T00:00:00Z")]  # 10% drift
    findings = check_doc_drift(
        impl(metrics=metrics),
        ctx(
            "GOV-006",
            category="governance_posture",
            threshold=0.20,
            last_sdr_update_at="2026-02-01",
        ),
    )
    assert findings == []


# ---------------------------------------------------------------------------
# SCH-006 cardinality_concerns
# ---------------------------------------------------------------------------


def test_cardinality_no_op_without_supplementary_data():
    dims = [component(i, comp_type="dimension", name="status flag") for i in range(3)]
    findings = check_cardinality_concerns(
        impl(dimensions=dims), ctx("SCH-006"),
    )
    assert findings == []


def test_cardinality_fires_when_low_card_named_dim_has_many_values():
    dims = [
        component(1, comp_type="dimension", cid="variables/evar1", name="user status"),
        component(2, comp_type="dimension", cid="variables/evar2", name="campaign code"),
    ]
    base_impl = impl(dimensions=dims)
    base_impl.supplementary_data["cardinality"] = {
        "variables/evar1": 4200,    # status with 4200 values -> suspicious
        "variables/evar2": 80000,   # campaign isn't keyword-matched -> ignored
    }
    findings = check_cardinality_concerns(
        base_impl, ctx("SCH-006", low_cardinality_cap=10),
    )
    assert len(findings) == 1
    assert "variables/evar1" in findings[0].body[1].items[0]


# ---------------------------------------------------------------------------
# AAEVAR-001 distinct values
# ---------------------------------------------------------------------------


def test_evar_distinct_values_no_op_on_cja():
    dims = [component(1, comp_type="dimension", cid="variables/evar1")]
    base_impl = impl(platform="cja", dimensions=dims)
    base_impl.supplementary_data["cardinality"] = {"variables/evar1": 99999}
    findings = check_aa_evar_distinct_values(base_impl, ctx("AAEVAR-001"))
    assert findings == []


def test_evar_distinct_values_fires_on_high_cardinality_aa_evar():
    dims = [
        component(1, comp_type="dimension", cid="variables/evar1"),
        component(2, comp_type="dimension", cid="variables/prop1"),  # not eVar
    ]
    base_impl = impl(platform="aa", dimensions=dims)
    base_impl.supplementary_data["cardinality"] = {
        "variables/evar1": 50000,
        "variables/prop1": 50000,
    }
    findings = check_aa_evar_distinct_values(
        base_impl, ctx("AAEVAR-001", max_distinct=10000),
    )
    assert len(findings) == 1
    assert "variables/evar1" in findings[0].body[1].items[0]


# ---------------------------------------------------------------------------
# CJASTITCH-001 unstitched IDs
# ---------------------------------------------------------------------------


def test_stitching_no_op_without_signal():
    findings = check_cja_stitching_unstitched(
        impl(platform="cja"), ctx("CJASTITCH-001", max_unstitched_ratio=0.05),
    )
    assert findings == []


def test_stitching_fires_above_threshold_via_supplementary():
    base_impl = impl(platform="cja")
    base_impl.supplementary_data["stitching"] = {"unstitched_ratio": 0.12}
    findings = check_cja_stitching_unstitched(
        base_impl, ctx("CJASTITCH-001", max_unstitched_ratio=0.05),
    )
    assert len(findings) == 1
    assert "12.0%" in findings[0].title


def test_stitching_reads_from_raw_data_view_when_present():
    base_impl = impl(
        platform="cja",
        raw={"data_view": {"stitching": {"unstitched_ratio": 0.20}}},
    )
    findings = check_cja_stitching_unstitched(
        base_impl, ctx("CJASTITCH-001", max_unstitched_ratio=0.05),
    )
    assert len(findings) == 1


def test_stitching_quiet_below_threshold():
    base_impl = impl(platform="cja")
    base_impl.supplementary_data["stitching"] = {"unstitched_ratio": 0.01}
    findings = check_cja_stitching_unstitched(
        base_impl, ctx("CJASTITCH-001", max_unstitched_ratio=0.05),
    )
    assert findings == []

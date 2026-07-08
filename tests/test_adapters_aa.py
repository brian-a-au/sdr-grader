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
STRICT_PACK = Path(__file__).resolve().parent.parent / "src" / "sdr_grader" / "rules" / "packs" / "strict"


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
    # Definition has visitors > visits + hits — 3 distinct contexts at nesting depth >= 4.
    assert set(nested.container_types) == {"visitors", "visits", "hits"}
    assert nested.nesting_depth >= 4


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

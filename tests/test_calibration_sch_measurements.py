"""Pin SCH-003 calibration to the bundled rule's decision statistic."""

from __future__ import annotations

import sys
from pathlib import Path

from _rule_test_helpers import component, impl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import calibrate_thresholds as ct  # noqa: E402


def _components(
    count: int,
    missing: int,
    *,
    component_type: str,
    prefix: str,
):
    return [
        component(
            index,
            comp_type=component_type,
            cid=f"{prefix}/{index}",
            description=None if index < missing else "documented",
        )
        for index in range(count)
    ]


def test_sch_003_targets_come_from_strict_pack():
    assert ct.SCH_003_TARGETS == ("metrics", "dimensions")


def test_sch_003_uses_maximum_per_target_ratio_not_aggregate():
    implementation = impl(
        metrics=_components(10, 9, component_type="metric", prefix="metrics"),
        dimensions=_components(
            90,
            0,
            component_type="dimension",
            prefix="dimensions",
        ),
    )

    assert ct._sch_missing_desc_ratio(implementation) == (0.9, 10)


def test_sch_003_excludes_derived_fields_not_configured_by_pack():
    implementation = impl(
        metrics=_components(10, 1, component_type="metric", prefix="metrics"),
        dimensions=_components(
            20,
            4,
            component_type="dimension",
            prefix="dimensions",
        ),
        derived=_components(
            100,
            100,
            component_type="derived_field",
            prefix="derived",
        ),
    )

    assert ct._sch_missing_desc_ratio(implementation) == (0.2, 20)


def test_sch_003_empty_configured_populations_have_empty_denominator():
    implementation = impl(
        derived=_components(
            5,
            5,
            component_type="derived_field",
            prefix="derived",
        )
    )

    assert ct._sch_missing_desc_ratio(implementation) == (0.0, 0)

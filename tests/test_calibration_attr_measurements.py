"""Pin the ATTR measurement functions in scripts/calibrate_thresholds.py.

These functions feed the threshold-calibration report (the input that
decides whether ATTR-001/002/003 thresholds are evidence-driven or
expert-judgment). Their semantics must match the corresponding rule
check logic in src/sdr_grader/rules/checks/attribution.py — if either
side drifts, the calibration data lies about what the rule will fire on.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _rule_test_helpers import calc, impl

# The calibration script isn't an installed module; import by file path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import calibrate_thresholds as ct  # noqa: E402

# ---------------------------------------------------------------------------
# ATTR-001 — silent-last-touch ratio on revenue/conversion calc metrics
# ---------------------------------------------------------------------------


def test_attr_001_empty_implementation_returns_zero_denominator():
    """No calc metrics → no observation. Calibration must skip these
    rather than treat them as 0% silent-last-touch."""
    assert ct._attr_silent_last_touch_ratio(impl()) == (0.0, 0)


def test_attr_001_no_revenue_named_calc_metrics_returns_zero_denominator():
    """Calc metrics exist but none match the revenue/conversion regex."""
    i = impl(calc=[calc("cm_pv_per_visit", name="Pageviews per Visit")])
    assert ct._attr_silent_last_touch_ratio(i) == (0.0, 0)


def test_attr_001_counts_attribution_none_as_silent():
    """The rule treats attribution_model=None as 'silently defaulting to
    last-touch' — calibration must mirror that semantics."""
    i = impl(
        calc=[
            calc("cm_revenue", name="Revenue", attribution_model=None),
        ]
    )
    ratio, n = ct._attr_silent_last_touch_ratio(i)
    assert ratio == 1.0
    assert n == 1


def test_attr_001_documented_last_touch_excluded():
    """A calc metric whose description mentions 'attribution' is a
    deliberate, documented choice — not silent."""
    i = impl(
        calc=[
            calc(
                "cm_revenue_documented",
                name="Revenue (last touch)",
                attribution_model="last-touch",
                description="Uses last-touch attribution per finance team request.",
            ),
        ]
    )
    assert ct._attr_silent_last_touch_ratio(i) == (0.0, 1)


def test_attr_001_explicit_non_last_touch_excluded():
    """First-touch / linear / etc. on a revenue metric is a deliberate
    choice the calibration does not treat as silent."""
    i = impl(calc=[calc("cm_rev_ft", name="Revenue (FT)", attribution_model="first-touch")])
    assert ct._attr_silent_last_touch_ratio(i) == (0.0, 1)


# ---------------------------------------------------------------------------
# ATTR-002 — overall calc-metric attribution-coverage ratio
# ---------------------------------------------------------------------------


def test_attr_002_empty_returns_zero_denominator():
    assert ct._attr_missing_ratio(impl()) == (0.0, 0)


def test_attr_002_all_missing_returns_one():
    i = impl(
        calc=[
            calc("a", attribution_model=None),
            calc("b", attribution_model=None),
            calc("c", attribution_model=None),
        ]
    )
    assert ct._attr_missing_ratio(i) == (1.0, 3)


def test_attr_002_partial_coverage():
    i = impl(
        calc=[
            calc("a", attribution_model="last-touch"),
            calc("b", attribution_model=None),
            calc("c", attribution_model=None),
            calc("d", attribution_model="first-touch"),
        ]
    )
    ratio, n = ct._attr_missing_ratio(i)
    assert ratio == 0.5
    assert n == 4


# ---------------------------------------------------------------------------
# ATTR-003 — count of (same-refs, ≥2 distinct attribution models) groups
# ---------------------------------------------------------------------------


def test_attr_003_empty_returns_zero():
    assert ct._attr_inconsistency_count(impl()) == (0.0, 0)


def test_attr_003_metrics_without_refs_or_attribution_skipped():
    i = impl(
        calc=[
            calc("a"),  # neither
            calc("b", attribution_model="last-touch"),  # no refs
            calc("c", references=["m_x"]),  # no attribution
        ]
    )
    assert ct._attr_inconsistency_count(i) == (0.0, 0)


def test_attr_003_same_refs_same_model_not_a_conflict():
    """Two metrics over the same refs with the same model is duplication,
    not inconsistency. Different rule, different category."""
    i = impl(
        calc=[
            calc("a", attribution_model="last-touch", references=["m_revenue"]),
            calc("b", attribution_model="last-touch", references=["m_revenue"]),
        ]
    )
    conflicts, eligible = ct._attr_inconsistency_count(i)
    assert conflicts == 0.0
    assert eligible == 2


def test_attr_003_one_conflict_group():
    i = impl(
        calc=[
            calc("a", attribution_model="last-touch", references=["m_revenue"]),
            calc("b", attribution_model="first-touch", references=["m_revenue"]),
            # Different refs — separate group, no conflict.
            calc("c", attribution_model="linear", references=["m_visits"]),
        ]
    )
    conflicts, eligible = ct._attr_inconsistency_count(i)
    assert conflicts == 1.0
    assert eligible == 3


def test_attr_003_multiple_conflict_groups():
    """Two independent refsets that each carry ≥2 distinct attribution
    models — count is 2."""
    i = impl(
        calc=[
            calc("a", attribution_model="last-touch", references=["m_revenue"]),
            calc("b", attribution_model="first-touch", references=["m_revenue"]),
            calc("c", attribution_model="linear", references=["m_orders"]),
            calc("d", attribution_model="u-shaped", references=["m_orders"]),
        ]
    )
    conflicts, eligible = ct._attr_inconsistency_count(i)
    assert conflicts == 2.0
    assert eligible == 4

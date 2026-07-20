"""Boundary tests for shared rule helpers."""

from __future__ import annotations

from _rule_test_helpers import calc, impl
from sdr_grader.rules.checks._helpers import (
    all_calc_metric_ids,
    join_with_and,
    parse_platform_setting,
    pct,
)


def test_percentage_returns_zero_for_nonpositive_denominator():
    assert pct(4, 0) == 0


def test_join_with_and_handles_empty_and_plural_inputs():
    assert join_with_and([]) == ""
    assert join_with_and(["a", "b", "c"]) == "a, b, and c"


def test_all_calc_metric_ids_collects_each_identifier():
    implementation = impl(calc=[calc("calc/a"), calc("calc/b")])
    assert all_calc_metric_ids(implementation) == {"calc/a", "calc/b"}


def test_parse_platform_setting_accepts_mappings_and_rejects_other_types():
    assert parse_platform_setting({"enabled": True}) == {"enabled": True}
    assert parse_platform_setting(42) is None

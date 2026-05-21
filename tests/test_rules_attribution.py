"""Tests for attribution_coverage rules (ATTR-*)."""

from __future__ import annotations

from _rule_test_helpers import calc, ctx, impl
from sdr_grader.core.models import Component
from sdr_grader.rules.checks.attribution import (
    check_attribution_default_last_touch,
    check_attribution_inconsistency,
    check_attribution_missing,
    check_attribution_setting_undocumented,
)


# ATTR-001
def test_attr001_fires_on_revenue_metric_with_default_last_touch():
    cms = [
        calc("cm_revenue", name="Revenue per Visit", attribution_model=None),
        calc("cm_other", name="Pageviews per Visit", attribution_model=None),
    ]
    findings = check_attribution_default_last_touch(
        impl(calc=cms), ctx("ATTR-001", category="attribution_coverage"),
    )
    assert len(findings) == 1
    assert "1 undocumented" in findings[0].title


def test_attr001_quiet_when_attribution_documented_in_description():
    cms = [
        calc(
            "cm_revenue",
            name="Revenue per Visit",
            attribution_model=None,
            description="Documented attribution choice: last-touch by team policy.",
        ),
    ]
    findings = check_attribution_default_last_touch(
        impl(calc=cms), ctx("ATTR-001", category="attribution_coverage"),
    )
    assert findings == []


def test_attr001_quiet_for_non_revenue_metrics():
    cms = [calc("cm_pages_per_visit", name="Pages per Visit", attribution_model=None)]
    findings = check_attribution_default_last_touch(
        impl(calc=cms), ctx("ATTR-001", category="attribution_coverage"),
    )
    assert findings == []


def test_attr001_quiet_when_explicit_non_last_touch_model():
    cms = [calc("cm_revenue", name="Revenue", attribution_model="linear")]
    findings = check_attribution_default_last_touch(
        impl(calc=cms), ctx("ATTR-001", category="attribution_coverage"),
    )
    assert findings == []


# ATTR-002
def test_attr002_fires_when_majority_lack_attribution():
    cms = [calc(f"c{i}", attribution_model=None) for i in range(7)]
    cms += [calc(f"c{i + 7}", attribution_model="linear") for i in range(3)]
    findings = check_attribution_missing(
        impl(calc=cms), ctx("ATTR-002", category="attribution_coverage", threshold=0.30),
    )
    assert len(findings) == 1


def test_attr002_quiet_when_most_specified():
    cms = [calc(f"c{i}", attribution_model="linear") for i in range(8)]
    cms += [calc(f"c{i + 8}", attribution_model=None) for i in range(2)]
    findings = check_attribution_missing(
        impl(calc=cms), ctx("ATTR-002", category="attribution_coverage", threshold=0.30),
    )
    assert findings == []


# ATTR-003
def test_attr003_fires_when_same_refs_different_models():
    refs = ["metrics/orders", "metrics/visits"]
    cms = [
        calc("a", references=list(refs), attribution_model="last-touch"),
        calc("b", references=list(refs), attribution_model="linear"),
    ]
    findings = check_attribution_inconsistency(
        impl(calc=cms), ctx("ATTR-003", category="attribution_coverage"),
    )
    assert len(findings) == 1


def test_attr003_quiet_when_same_model_across_group():
    refs = ["metrics/orders", "metrics/visits"]
    cms = [
        calc("a", references=list(refs), attribution_model="last-touch"),
        calc("b", references=list(refs), attribution_model="last-touch"),
    ]
    findings = check_attribution_inconsistency(
        impl(calc=cms), ctx("ATTR-003", category="attribution_coverage"),
    )
    assert findings == []


# ---------------------------------------------------------------------------
# ATTR-004: non-default Data View attribution without description mention
# ---------------------------------------------------------------------------


def _metric_with_attribution(idx: int, setting, *, description: str | None = "ok") -> Component:
    return Component(
        id=f"metrics/m_{idx:03d}",
        name=f"Metric {idx:03d}",
        description=description,
        component_type="metric",
        data_type="integer",
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=None,
        tags=[],
        platform_specific={"attributionSetting": setting},
    )


_ENABLED_LAST_TOUCH = (
    '{"enabled":true,"attributionModel":{"func":"allocation-lastTouch",'
    '"expiration":{"context":"sessions","func":"allocation-container"}}}'
)


def test_attr004_no_op_on_aa():
    metrics = [_metric_with_attribution(1, _ENABLED_LAST_TOUCH)]
    findings = check_attribution_setting_undocumented(
        impl(platform="aa", metrics=metrics),
        ctx("ATTR-004", category="attribution_coverage"),
    )
    assert findings == []


def test_attr004_quiet_when_attributionsetting_disabled():
    metrics = [_metric_with_attribution(1, '{"enabled":false}')]
    findings = check_attribution_setting_undocumented(
        impl(metrics=metrics),
        ctx("ATTR-004", category="attribution_coverage"),
    )
    assert findings == []


def test_attr004_fires_when_enabled_and_description_silent():
    metrics = [
        _metric_with_attribution(1, _ENABLED_LAST_TOUCH, description="Sum of orders."),
    ]
    findings = check_attribution_setting_undocumented(
        impl(metrics=metrics),
        ctx("ATTR-004", category="attribution_coverage"),
    )
    assert len(findings) == 1
    assert "1 metric" in findings[0].title


def test_attr004_quiet_when_description_mentions_attribution():
    metrics = [
        _metric_with_attribution(
            1, _ENABLED_LAST_TOUCH,
            description="Sum of orders using last-touch attribution by analyst request.",
        ),
    ]
    findings = check_attribution_setting_undocumented(
        impl(metrics=metrics),
        ctx("ATTR-004", category="attribution_coverage"),
    )
    assert findings == []


def test_attr004_handles_nan_sentinel():
    metrics = [_metric_with_attribution(1, float("nan"))]
    findings = check_attribution_setting_undocumented(
        impl(metrics=metrics),
        ctx("ATTR-004", category="attribution_coverage"),
    )
    assert findings == []

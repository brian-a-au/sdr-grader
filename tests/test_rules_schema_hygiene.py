"""Tests for rules/checks/schema_hygiene.py SCH-003 (missing_descriptions)."""

from __future__ import annotations

from typing import Any

from sdr_grader.core.models import Component, Implementation
from sdr_grader.rules.checks.schema_hygiene import check_missing_descriptions
from sdr_grader.rules.engine import RuleContext


def _component(component_type: str, idx: int, *, description: str | None) -> Component:
    return Component(
        id=f"id_{idx}",
        name=f"name_{idx}",
        description=description,
        component_type=component_type,  # type: ignore[arg-type]
        data_type="string",
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=None,
    )


def _impl(*,
    metrics: list[Component] | None = None,
    dimensions: list[Component] | None = None,
    derived: list[Component] | None = None,
) -> Implementation:
    return Implementation(
        platform="cja",
        instance_id="dv_test",
        instance_name="Test",
        snapshot_taken_at=None,
        snapshot_source="test",
        adapter_version="0",
        metrics=metrics or [],
        dimensions=dimensions or [],
        segments=[],
        calculated_metrics=[],
        derived_fields=derived or [],
        raw={},
    )


def _ctx(**params: Any) -> RuleContext:
    return RuleContext(
        rule_id="SCH-003",
        rule_name="Components lacking descriptions",
        severity="medium",
        category="schema_hygiene",
        platforms=["cja", "aa"],
        params=params,
        rationale="ratio.",
        remediation="populate descriptions.",
    )


def test_no_findings_when_all_components_documented():
    impl = _impl(
        metrics=[_component("metric", i, description=f"m{i}") for i in range(20)],
        dimensions=[_component("dimension", i, description=f"d{i}") for i in range(30)],
    )
    findings = check_missing_descriptions(impl, _ctx(threshold=0.10, targets=["metrics", "dimensions"]))
    assert findings == []


def test_no_findings_when_rate_below_threshold():
    metrics = [_component("metric", i, description="ok") for i in range(95)]
    metrics += [_component("metric", i, description=None) for i in range(5)]  # 5 / 100 = 5%
    impl = _impl(metrics=metrics)
    findings = check_missing_descriptions(impl, _ctx(threshold=0.10, targets=["metrics"]))
    assert findings == []


def test_finding_emitted_when_rate_exceeds_threshold():
    metrics = [_component("metric", i, description="ok") for i in range(80)]
    metrics += [_component("metric", i, description=None) for i in range(20)]  # 20%
    impl = _impl(metrics=metrics)
    findings = check_missing_descriptions(impl, _ctx(threshold=0.10, targets=["metrics"]))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.id == "SCH-003"
    assert finding.severity == "medium"
    assert finding.title == "20 components lack descriptions"
    assert "20 metrics" in finding.body[0].html
    distribution = finding.body[1].body_html
    assert "20 of 100 missing (20%)" in distribution
    assert "rubric threshold is 10%" in distribution


def test_finding_aggregates_across_targets_above_threshold():
    metrics = [_component("metric", i, description="ok") for i in range(140)]
    metrics += [_component("metric", i, description=None) for i in range(20)]
    dimensions = [_component("dimension", i, description="ok") for i in range(180)]
    dimensions += [_component("dimension", i, description=None) for i in range(40)]  # ~18%
    impl = _impl(metrics=metrics, dimensions=dimensions)
    findings = check_missing_descriptions(
        impl, _ctx(threshold=0.10, targets=["metrics", "dimensions"])
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.title == "60 components lack descriptions"
    assert "20 metrics and 40 dimensions" in finding.body[0].html


def test_finding_excludes_targets_under_threshold():
    metrics = [_component("metric", i, description="ok") for i in range(95)]
    metrics += [_component("metric", i, description=None) for i in range(5)]  # 5%, under
    dimensions = [_component("dimension", i, description="ok") for i in range(70)]
    dimensions += [_component("dimension", i, description=None) for i in range(30)]  # 30%, over
    impl = _impl(metrics=metrics, dimensions=dimensions)
    findings = check_missing_descriptions(
        impl, _ctx(threshold=0.10, targets=["metrics", "dimensions"])
    )
    assert len(findings) == 1
    finding = findings[0]
    # Only dimensions exceeded; metrics should not appear in the finding body.
    assert "30 dimensions" in finding.body[0].html
    assert "5 metrics" not in finding.body[0].html


def test_default_targets_include_metrics_dimensions_derived_fields():
    derived = [_component("derived_field", i, description="ok") for i in range(80)]
    derived += [_component("derived_field", i, description=None) for i in range(20)]  # 20%
    impl = _impl(derived=derived)
    # No explicit targets -> defaults exercised.
    findings = check_missing_descriptions(impl, _ctx(threshold=0.10))
    assert len(findings) == 1
    assert "20 derived fields" in findings[0].body[0].html


def test_finding_includes_remediation_section_when_rule_has_one():
    metrics = [_component("metric", i, description=None) for i in range(20)]
    impl = _impl(metrics=metrics)
    findings = check_missing_descriptions(impl, _ctx(threshold=0.10, targets=["metrics"]))
    finding = findings[0]
    labels = [block.label for block in finding.body if block.kind == "section"]
    assert "How to remediate" in labels


def test_blank_target_section_does_not_crash():
    impl = _impl()  # no metrics, no dimensions, no derived
    findings = check_missing_descriptions(
        impl, _ctx(threshold=0.10, targets=["metrics", "dimensions", "derived_fields"])
    )
    assert findings == []

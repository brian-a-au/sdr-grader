"""Focused tests for grader orchestration seams."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sdr_grader.adapters.cja import adapt
from sdr_grader.core.grade_calc import CategoryScore, GradeResult
from sdr_grader.core.grader import _build_tldr, _derive_remediations, grade
from sdr_grader.core.models import Implementation
from sdr_grader.render import Finding, FindingBlock, render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.engine import resolve_effective_rules, run_rules
from sdr_grader.rules.rubric import GradeBand, Rubric, RuleDefinition


def _impl(platform: str = "aa") -> Implementation:
    return Implementation(
        platform=platform,  # type: ignore[arg-type]
        instance_id="test",
        instance_name="Test",
        snapshot_taken_at=None,
        snapshot_source="test",
        adapter_version="1",
        metrics=[],
        dimensions=[],
        segments=[],
        calculated_metrics=[],
        derived_fields=[],
        raw={},
    )


def _rule(rule_id: str, platforms: list[str]) -> RuleDefinition:
    return RuleDefinition(
        id=rule_id,
        name=rule_id,
        severity="medium",
        platforms=platforms,
        check="test-check",
        category="schema_hygiene",
    )


def _rubric(rules: list[RuleDefinition]) -> Rubric:
    return Rubric(
        pack="test",
        version="1",
        description="",
        category_weights={"schema_hygiene": 1.0},
        severity_weights={"critical": 4, "high": 3, "medium": 2, "low": 1},
        grade_scale=[GradeBand(min_score=0, grade="F")],
        rules=rules,
    )


def test_effective_rules_preserve_order_and_exclude_platform_and_suppressed_rules():
    rules = [
        _rule("COMMON-1", []),
        _rule("CJA-1", ["cja"]),
        _rule("AA-1", ["aa"]),
        _rule("COMMON-2", ["aa", "cja"]),
    ]

    inventory = resolve_effective_rules(
        _impl("aa"),
        _rubric(rules),
        excluded_rule_ids={"COMMON-2"},
    )

    assert [rule.id for rule in inventory] == ["COMMON-1", "AA-1"]


def test_rule_engine_defaults_to_the_platform_inventory(monkeypatch):
    rules = [
        _rule("COMMON-1", []),
        _rule("CJA-1", ["cja"]),
        _rule("AA-1", ["aa"]),
    ]
    executed: list[str] = []

    def get_recording_check(_name):
        def record(_impl, context):
            executed.append(context.rule_id)
            return []

        return record

    monkeypatch.setattr("sdr_grader.rules.engine.get_check", get_recording_check)

    assert run_rules(_impl("aa"), _rubric(rules)) == []
    assert executed == ["COMMON-1", "AA-1"]


def test_rule_engine_propagates_check_exceptions(monkeypatch):
    rule = _rule("AA-1", ["aa"])

    def explode(_impl, _context):
        raise RuntimeError("check failed")

    monkeypatch.setattr("sdr_grader.rules.engine.get_check", lambda _name: explode)

    with pytest.raises(RuntimeError, match="check failed"):
        run_rules(_impl(), _rubric([rule]), rule_inventory=(rule,))


def test_rule_engine_rejects_findings_for_another_rule(monkeypatch):
    rule = _rule("AA-1", ["aa"])
    wrong_finding = Finding(
        id="OTHER-1",
        severity="medium",
        category="schema hygiene",
        title="Wrong rule",
        body=[FindingBlock(kind="paragraph", html="x")],
    )
    monkeypatch.setattr(
        "sdr_grader.rules.engine.get_check",
        lambda _name: lambda _impl, _context: [wrong_finding],
    )

    with pytest.raises(ValueError, match="finding IDs for other rules"):
        run_rules(_impl(), _rubric([rule]), rule_inventory=(rule,))


def test_remediations_skip_rules_without_remediation_text():
    rule = RuleDefinition(
        id="TEST-EMPTY",
        name="No remediation",
        severity="medium",
        platforms=["cja"],
        check="unused-in-direct-test",
        category="schema_hygiene",
        remediation="",
    )
    finding = Finding(
        id=rule.id,
        severity="medium",
        category="schema hygiene",
        title="Finding without remediation",
        body=[FindingBlock(kind="paragraph", html="Observed behavior")],
    )
    assert _derive_remediations({rule.id: rule}, [finding]) == []


def test_remediation_uses_truthful_priority_weight_with_legacy_alias():
    rule = RuleDefinition(
        id="TEST-HIGH",
        name="High-priority repair",
        severity="high",
        platforms=["cja"],
        check="unused-in-direct-test",
        category="schema_hygiene",
        remediation="Repair the observed configuration.",
    )
    finding = Finding(
        id=rule.id,
        severity="high",
        category="schema hygiene",
        title="Observed gap",
        body=[FindingBlock(kind="paragraph", html="Observed behavior")],
    )

    remediation = _derive_remediations({rule.id: rule}, [finding])[0]

    assert remediation.priority_weight == 5
    assert remediation.impact_pts == remediation.priority_weight


def test_real_cja_pdt_timestamp_flows_to_report_html_and_json():
    impl = adapt(
        {
            "metadata": {
                "Data View ID": "dv-real",
                "Data View Name": "Real export",
                "Generated Date & timestamp and timezone": "2026-05-20 10:56:29 PDT",
            },
            "metrics": [],
            "dimensions": [],
        }
    )

    report = grade(impl, _rubric([]))
    html = render(report)
    data = report_to_dict(report)

    assert report.generated_at.isoformat() == "2026-05-20T17:56:29+00:00"
    assert report.id == "SDR-2026-0520-DV-REAL"
    assert "May 20 2026 · 17:56 UTC" in html
    assert data["generated_at"] == "2026-05-20T17:56:29Z"


def test_tldr_trusted_markup_escapes_dynamic_rubric_values():
    rubric = replace(
        _rubric([]),
        pack='<img src="https://attacker.invalid" onerror="alert(1)">',
        version="<script>alert(2)</script>",
    )
    result = GradeResult(
        overall_pct=100,
        overall_grade="A",
        categories=[
            CategoryScore(
                slug="schema_hygiene",
                weight=1.0,
                pct=100,
                grade="A",
                rules_total=0,
                rules_failed=0,
            )
        ],
    )

    markup = _build_tldr(_impl(), rubric, result)

    assert "<img" not in markup
    assert "<script" not in markup
    assert "&lt;img" in markup
    assert "&lt;script" in markup
    assert "<strong>A</strong>" in markup

"""Focused tests for grader orchestration seams."""

from __future__ import annotations

from sdr_grader.core.grader import _derive_remediations
from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.rubric import RuleDefinition


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

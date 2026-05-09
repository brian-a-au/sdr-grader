"""Rule runner.

Given a normalized Implementation and a loaded Rubric, produces the list of
Findings the grader assembles into a Report. Checks are pure functions;
this module is the only place that calls them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sdr_grader.core.models import Implementation
from sdr_grader.render import Finding
from sdr_grader.rules.registry import get_check
from sdr_grader.rules.rubric import Rubric, RuleDefinition


@dataclass(frozen=True)
class RuleContext:
    """Per-rule execution context handed to each check function."""

    rule_id: str
    rule_name: str
    severity: str
    category: str
    platforms: list[str]
    params: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    remediation: str = ""


def run_rules(impl: Implementation, rubric: Rubric) -> list[Finding]:
    """Execute every rule in the rubric applicable to the implementation."""
    findings: list[Finding] = []
    for rule in rubric.rules:
        if not _applies_to_platform(rule, impl):
            continue
        ctx = _build_context(rule)
        check = get_check(rule.check)
        produced = check(impl, ctx)
        findings.extend(produced)
    return findings


def _applies_to_platform(rule: RuleDefinition, impl: Implementation) -> bool:
    if not rule.platforms:
        return True
    return impl.platform in rule.platforms


def _build_context(rule: RuleDefinition) -> RuleContext:
    return RuleContext(
        rule_id=rule.id,
        rule_name=rule.name,
        severity=rule.severity,
        category=rule.category,
        platforms=list(rule.platforms),
        params=dict(rule.params),
        rationale=rule.rationale,
        remediation=rule.remediation,
    )

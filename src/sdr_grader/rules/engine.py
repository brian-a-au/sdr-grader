"""Rule runner.

Given a normalized Implementation and a loaded Rubric, produces the list of
Findings the grader assembles into a Report. Checks are pure functions;
this module is the only place that calls them.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
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


RuleInventory = tuple[RuleDefinition, ...]


def resolve_effective_rules(
    impl: Implementation,
    rubric: Rubric,
    *,
    excluded_rule_ids: Collection[str] = (),
) -> RuleInventory:
    """Return the ordered rules that can affect this implementation."""
    excluded = set(excluded_rule_ids)
    return tuple(
        rule
        for rule in rubric.rules
        if rule.id not in excluded and _applies_to_platform(rule, impl)
    )


def run_rules(
    impl: Implementation,
    rubric: Rubric,
    *,
    rule_inventory: Sequence[RuleDefinition] | None = None,
) -> list[Finding]:
    """Execute one resolved rule inventory for the implementation."""
    rules = (
        resolve_effective_rules(impl, rubric)
        if rule_inventory is None
        else rule_inventory
    )
    findings: list[Finding] = []
    for rule in rules:
        ctx = _build_context(rule)
        check = get_check(rule.check)
        produced = check(impl, ctx)
        unexpected_ids = {finding.id for finding in produced if finding.id != rule.id}
        if unexpected_ids:
            raise ValueError(
                f"check {rule.check!r} for rule {rule.id!r} returned "
                f"finding IDs for other rules: {sorted(unexpected_ids)!r}"
            )
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

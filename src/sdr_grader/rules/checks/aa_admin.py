"""AA-only configuration comparisons against explicitly declared expectations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sdr_grader.core.aa_admin import AA_CHECKS, assess_aa_admin
from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import make_finding
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


def _check(impl: Implementation, ctx: RuleContext, name: str) -> list[Finding]:
    if impl.platform != "aa":
        return []
    assessment = ctx.aa_admin_assessment or assess_aa_admin(impl, {name})[name]
    if assessment.not_assessed or not assessment.mismatches:
        return []
    return [
        make_finding(
            ctx,
            title=ctx.rule_name,
            paragraph="Observed configuration differs from explicitly declared business expectations. "
            "This check assesses configuration only; runtime behavior remains unverified.",
            extra_blocks=[FindingBlock(kind="components", items=list(assessment.mismatches))],
        )
    ]


def _register(name: str) -> None:
    def check(impl: Implementation, ctx: RuleContext) -> list[Finding]:
        return _check(impl, ctx, name)

    register_check(name)(check)


for _name in AA_CHECKS:
    _register(_name)

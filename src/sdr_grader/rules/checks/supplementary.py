"""Checks that consume --extra-input supplementary data.

These rules opt in by reading impl.supplementary_data[KEY]. If the key is
absent, the rule is silent — operators only get findings on the
supplementary data they actually attach.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import category_display, compact, pct
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# LAUNCH-001: required Launch data elements present
# ---------------------------------------------------------------------------


@register_check("launch_required_data_elements")
def check_launch_required_data_elements(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when a Launch property export is missing required data elements.

    Reads impl.supplementary_data['launch']. The expected shape:

        {
          "property": {"name": "Production Web"},
          "data_elements": [
            {"name": "page_name", "type": "..."},
            {"name": "user_id",   "type": "..."}
          ]
        }

    Required element names come from ctx.params['required'] (a list).
    Missing elements -> finding. Extra elements are ignored.
    """
    launch = impl.supplementary_data.get("launch")
    if not isinstance(launch, dict):
        return []
    required = list(ctx.params.get("required") or [])
    if not required:
        return []
    elements = launch.get("data_elements") or []
    if not isinstance(elements, list):
        return []
    present = {
        str(el.get("name"))
        for el in elements
        if isinstance(el, dict) and el.get("name")
    }
    missing = [name for name in required if name not in present]
    if not missing:
        return []
    paragraph = (
        f"{len(missing)} of {len(required)} required Launch data elements "
        f"({pct(len(missing), len(required))}%) are not defined on the property "
        f"{launch.get('property', {}).get('name', 'unknown')!r}. Without these "
        "data elements, downstream tags can't pick up the values they expect."
    )
    body = [
        FindingBlock(kind="paragraph", html=paragraph),
        FindingBlock(kind="components", items=[f"missing: {n}" for n in missing]),
    ]
    if ctx.remediation:
        body.append(
            FindingBlock(
                kind="section",
                label="How to remediate",
                body_html=compact(ctx.remediation),
            )
        )
    return [
        Finding(
            id=ctx.rule_id,
            severity=ctx.severity,  # type: ignore[arg-type]
            category=category_display(ctx.category),
            title=f"{len(missing)} required Launch data element{'s' if len(missing) != 1 else ''} missing",
            body=body,
        )
    ]

"""HTML report renderer.

The visual contract (templates/ and static/) is locked. The renderer is a presentation layer:
it must work standalone with fabricated data and never call back into the rule
engine.
"""

from sdr_grader.render.renderer import (
    Adapter,
    Category,
    Distribution,
    DistributionChart,
    Finding,
    FindingAction,
    FindingBlock,
    Methodology,
    Remediation,
    Report,
    Rubric,
    Severity,
    SkippedRules,
    render,
)
from sdr_grader.render.truncation import (
    MAX_COMPONENT_ITEMS,
    cap_component_items,
)

__all__ = [
    "MAX_COMPONENT_ITEMS",
    "Adapter",
    "Category",
    "Distribution",
    "DistributionChart",
    "Finding",
    "FindingAction",
    "FindingBlock",
    "Methodology",
    "Remediation",
    "Report",
    "Rubric",
    "Severity",
    "SkippedRules",
    "cap_component_items",
    "render",
]

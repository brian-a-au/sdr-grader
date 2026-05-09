"""HTML report renderer.

The visual contract is locked (SPEC §3). The renderer is a presentation layer:
it must work standalone with fabricated data and never call back into the rule
engine (SPEC §4).
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

__all__ = [
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
    "render",
]

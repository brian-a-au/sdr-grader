"""Deterministic display cap for finding component lists (issue #5).

A finding's `components` block renders one <pre> line per affected
component — the only unbounded-size path into the HTML report. A single
rule matching thousands of components would otherwise produce a multi-MB
file. `cap_component_items` bounds the HTML presentation while staying
pure and deterministic: same input, same output, byte for byte.

Callers apply it upstream of render() — the renderer itself stays
presentation-only and renders its input verbatim. The `--json` artifact
is written from the uncapped Report, so the full component list is never
lost; only the HTML presentation is bounded.
"""

from __future__ import annotations

from dataclasses import replace

from sdr_grader.render.renderer import Finding, FindingBlock, Report

MAX_COMPONENT_ITEMS = 50


def cap_component_items(report: Report, cap: int = MAX_COMPONENT_ITEMS) -> Report:
    """Return `report` with every components block bounded to `cap` items.

    A truncated block keeps its first `cap` items (order preserved) and is
    followed by a paragraph block noting how many items were hidden. Blocks
    at or under the cap are untouched; if nothing is truncated, the input
    report is returned as-is. The input is never mutated.
    """
    capped = [_cap_finding(f, cap) for f in report.findings]
    if all(new is old for new, old in zip(capped, report.findings, strict=True)):
        return report
    return replace(report, findings=capped)


def _cap_finding(finding: Finding, cap: int) -> Finding:
    body: list[FindingBlock] = []
    truncated = False
    for block in finding.body:
        if block.kind != "components" or not block.items or len(block.items) <= cap:
            body.append(block)
            continue
        hidden = len(block.items) - cap
        body.append(replace(block, items=block.items[:cap]))
        body.append(
            FindingBlock(
                kind="paragraph",
                html=f"… and {hidden:,} more (see JSON output)",
            )
        )
        truncated = True
    return replace(finding, body=body) if truncated else finding

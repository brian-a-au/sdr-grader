"""Platform-specific checks: AA eVar discipline + CJA stitching.

Per SPEC §9 the platform-specific rules: AAEVAR-001, AAEVAR-002,
CJASTITCH-001. AAEVAR-001 and CJASTITCH-001 require platform data the
v0.1 snapshots don't expose; they're registered as no-ops with explicit
docstrings until upstream supplies the signals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import category_display, compact
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# AAEVAR-001: eVars carrying semantically distinct values (stub)
# ---------------------------------------------------------------------------


@register_check("aa_evar_distinct_values")
def check_aa_evar_distinct_values(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Cardinality/correlation analysis is out of scope for v0.1.

    Requires per-eVar value distributions which neither cja_auto_sdr nor
    aa_auto_sdr ships in their JSON output today. Tracked under SPEC §13
    open questions; implement when upstream supplies cardinality.
    """
    return []


# ---------------------------------------------------------------------------
# AAEVAR-002: eVars with conflicting allocation/expiration combinations
# ---------------------------------------------------------------------------


_DEFAULT_BAD_COMBINATIONS: list[tuple[str, str]] = [
    ("linear", "hit"),
    ("linear", "page-view"),
    ("most-recent", "visitor"),
]


@register_check("aa_evar_allocation_expiration")
def check_aa_evar_allocation_expiration(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire on eVars whose (allocation, expiration) pair is in the bad set."""
    if impl.platform != "aa":
        return []

    bad_combos_raw = ctx.params.get("bad_combinations") or [
        list(combo) for combo in _DEFAULT_BAD_COMBINATIONS
    ]
    bad_combos = {(_norm(a), _norm(b)) for a, b in bad_combos_raw}

    suspects: list[tuple[str, str, str]] = []  # (id, allocation, expiration)
    for d in impl.dimensions:
        if not d.id.startswith("variables/evar"):
            continue
        extra = d.platform_specific.get("extra") or {}
        alloc = _norm(extra.get("allocation"))
        expir = _norm(extra.get("expiration"))
        if not alloc or not expir:
            continue
        if (alloc, expir) in bad_combos:
            suspects.append((d.id, alloc, expir))

    if not suspects:
        return []
    items = [f"{eid}  allocation={a}, expiration={e}" for eid, a, e in suspects[:25]]
    paragraph = (
        f"{len(suspects)} eVar{'s have' if len(suspects) != 1 else ' has'} an "
        "allocation / expiration combination flagged by the rubric. The pairing "
        "produces counterintuitive attribution behavior that surfaces as "
        "&ldquo;the numbers don't roll up&rdquo; complaints."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(suspects)} eVar configuration mismatch{'es' if len(suspects) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


def _norm(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("_", "-")


# ---------------------------------------------------------------------------
# CJASTITCH-001: stitching configuration has unstitched IDs above threshold (stub)
# ---------------------------------------------------------------------------


@register_check("cja_stitching_unstitched")
def check_cja_stitching_unstitched(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Stitching configuration is not present in cja_auto_sdr's JSON today.

    Implement when upstream exposes stitching metadata on the data view.
    """
    return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    ctx: RuleContext, *, title: str, paragraph: str,
    extra_blocks: list[FindingBlock] | None = None,
) -> Finding:
    body: list[FindingBlock] = [FindingBlock(kind="paragraph", html=paragraph)]
    if extra_blocks:
        body.extend(extra_blocks)
    if ctx.remediation:
        body.append(
            FindingBlock(
                kind="section",
                label="How to remediate",
                body_html=compact(ctx.remediation),
            )
        )
    return Finding(
        id=ctx.rule_id,
        severity=ctx.severity,  # type: ignore[arg-type]
        category=category_display(ctx.category),
        title=title,
        body=body,
    )

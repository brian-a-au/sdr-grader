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
    """Fire on eVars carrying many distinct values (a high-cardinality smell).

    Reads per-eVar distinct-value counts from
    impl.supplementary_data['cardinality'] when present (mapping of
    component_id -> int). Operators populate it via --extra-input
    cardinality=PATH; the same key is shared with SCH-006.

    Without cardinality data, the rule is a no-op.
    """
    if impl.platform != "aa":
        return []
    cardinalities = impl.supplementary_data.get("cardinality") or {}
    if not isinstance(cardinalities, dict) or not cardinalities:
        return []
    cap = int(ctx.params.get("max_distinct", 10000))
    suspects: list[tuple[str, str, int]] = []
    for d in impl.dimensions:
        if not d.id.startswith("variables/evar"):
            continue
        n = cardinalities.get(d.id)
        if not isinstance(n, int) or n <= cap:
            continue
        suspects.append((d.id, d.name, n))
    if not suspects:
        return []
    items = [f"{eid}  name={name!r}  distinct={n}" for eid, name, n in suspects[:25]]
    paragraph = (
        f"{len(suspects)} eVar{'s carry' if len(suspects) != 1 else ' carries'} "
        f"more than {cap} distinct values. High cardinality on a single eVar "
        "usually means it's mixing semantically distinct domains; the eVar "
        "should be split."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(suspects)} high-cardinality eVar{'s' if len(suspects) != 1 else ''}",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=items)],
        )
    ]


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
    """Fire when stitching reports a high unstitched-IDs ratio.

    Reads stitching state from impl.supplementary_data['stitching'] (a JSON
    object like {"unstitched_ratio": 0.12}) or from
    impl.raw['data_view']['stitching']['unstitched_ratio'] when upstream
    eventually exposes it. Operators attach it via --extra-input
    stitching=PATH.

    Without that data the rule is a no-op.
    """
    if impl.platform != "cja":
        return []
    cap = float(ctx.params.get("max_unstitched_ratio", 0.05))
    ratio = None
    supp = impl.supplementary_data.get("stitching")
    if isinstance(supp, dict):
        ratio = supp.get("unstitched_ratio")
    if ratio is None and isinstance(impl.raw, dict):
        dv = impl.raw.get("data_view")
        if isinstance(dv, dict):
            stitch = dv.get("stitching")
            if isinstance(stitch, dict):
                ratio = stitch.get("unstitched_ratio")
    try:
        ratio_value = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        ratio_value = None
    if ratio_value is None or ratio_value <= cap:
        return []
    paragraph = (
        f"Stitching reports {round(ratio_value * 100, 1)}% of identifiers "
        f"unstitched; the rubric flags above {round(cap * 100, 1)}%. "
        "Unstitched IDs fragment cross-device journeys and undercount unique "
        "users — retention and cohort analyses become unreliable above a "
        "small threshold."
    )
    return [
        _make_finding(
            ctx,
            title=f"Stitching: {round(ratio_value * 100, 1)}% unstitched IDs",
            paragraph=paragraph,
        )
    ]


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

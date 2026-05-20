"""Governance posture checks (GOV-001..GOV-006).

Some governance signals (snapshot history, SDR documentation, doc/code
parity) live outside the JSON snapshot the grader sees. Those rules accept
externally-supplied params or fall back to no-op behavior so the rubric
can still declare the intent without producing noisy false positives.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.checks._helpers import (
    all_components,
    category_display,
    compact,
    pct,
)
from sdr_grader.rules.registry import register_check

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.rules.engine import RuleContext


# ---------------------------------------------------------------------------
# GOV-001: no snapshot history detected
# ---------------------------------------------------------------------------


@register_check("snapshot_history_absent")
def check_snapshot_history_absent(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when no prior snapshots are reported alongside this one.

    Resolution order: ctx.params['history_present'] (pack-level override) ->
    snapshot metadata 'history_present' / 'History Present' -> assume worst
    (fire). The directory-mode loader and CI integrations can inject the
    metadata flag when they have evidence of history.
    """
    if _signal_present(impl, ctx, "history_present", "History Present"):
        return []
    paragraph = (
        "No prior snapshots of this implementation were detected alongside "
        "the input. Without snapshot history, configuration changes cannot "
        "be diffed, drift cannot be detected, and audit trails are unavailable "
        "for compliance review."
    )
    return [
        _make_finding(
            ctx,
            title="No snapshot history detected for this data view",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# GOV-002: snapshot exists but is stale
# ---------------------------------------------------------------------------


@register_check("snapshot_age")
def check_snapshot_age(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when the snapshot is older than `max_age_days`.

    Determinism: this rule needs a reference date. The caller supplies
    `reference_date` as ISO-8601 in params (typically the snapshot's own
    timestamp at load time). Without a reference, the rule is a no-op.
    """
    max_age_days = int(ctx.params.get("max_age_days", 90))
    reference_iso = ctx.params.get("reference_date")
    snapshot_iso = impl.snapshot_taken_at
    if not reference_iso or not snapshot_iso:
        return []
    snapshot_dt = _parse_iso(snapshot_iso)
    reference_dt = _parse_iso(str(reference_iso))
    if snapshot_dt is None or reference_dt is None:
        return []
    age_days = (reference_dt - snapshot_dt).days
    if age_days <= max_age_days:
        return []
    paragraph = (
        f"The snapshot is {age_days} days old (taken {snapshot_iso}). The "
        f"rubric flags snapshots older than {max_age_days} days because "
        "implementation drift makes them unreliable as audit baselines."
    )
    return [
        _make_finding(
            ctx,
            title=f"Snapshot is {age_days} days old",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# GOV-003: no SDR documentation detected
# ---------------------------------------------------------------------------


@register_check("sdr_doc_absent")
def check_sdr_doc_absent(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when no SDR doc is signaled for this data view.

    Resolution order matches GOV-001: ctx.params['sdr_doc_present'] ->
    snapshot metadata 'sdr_doc_present' / 'SDR Doc Present' -> fire.
    """
    if _signal_present(impl, ctx, "sdr_doc_present", "SDR Doc Present"):
        return []
    # Default to firing; the operator can suppress via .sdr-grader.yaml if
    # they keep their SDR somewhere the grader can't see.
    paragraph = (
        "No Solution Design Reference (SDR) document was supplied alongside "
        "this snapshot. Without an SDR, definitions live only in the platform "
        "UI, which makes peer review and onboarding harder and obscures the "
        "&ldquo;why&rdquo; behind component choices."
    )
    return [
        _make_finding(
            ctx,
            title="No SDR documentation detected",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# GOV-004: components missing owner attribution
# ---------------------------------------------------------------------------


@register_check("missing_owners")
def check_missing_owners(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.10))
    components = all_components(impl)
    if not components:
        return []
    total = len(components)
    missing = sum(1 for c in components if not c.owner)
    if total == 0 or (missing / total) <= threshold:
        return []
    paragraph = (
        f"{missing} of {total} components ({pct(missing, total)}%) have no "
        "owner attribution. When a component has no owner, there is no clear "
        "person to ask for context, sign off on changes, or maintain its "
        "documentation."
    )
    return [
        _make_finding(
            ctx,
            title=f"{missing} components lack owner attribution",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# GOV-005: components missing tags / categorization
# ---------------------------------------------------------------------------


@register_check("missing_tags")
def check_missing_tags(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.50))
    components = all_components(impl)
    if not components:
        return []
    total = len(components)
    missing = sum(1 for c in components if not c.tags)
    if total == 0 or (missing / total) <= threshold:
        return []
    paragraph = (
        f"{missing} of {total} components ({pct(missing, total)}%) have no "
        "tags. Tags are the cheapest way to keep schema browsing tractable "
        "as the data view grows; without them, finding components by "
        "purpose requires reading every name."
    )
    return [
        _make_finding(
            ctx,
            title=f"{missing} components lack tags",
            paragraph=paragraph,
        )
    ]


# ---------------------------------------------------------------------------
# GOV-006: stale modifications without doc updates
# ---------------------------------------------------------------------------


@register_check("doc_drift")
def check_doc_drift(
    impl: Implementation, ctx: RuleContext
) -> list[Finding]:
    """Fire when components were modified after the last documented SDR update.

    Inputs (in priority order):
    - ctx.params['last_sdr_update_at']: ISO date the SDR was last updated.
    - impl.supplementary_data['sdr']['last_updated_at']: same, sourced from
      a Wiki / Confluence / Notion export attached via --extra-input sdr=PATH.
    - impl.raw['metadata']['SDR Last Updated']: same, when upstream supplies it.

    Without any of those, the rule is a no-op so it doesn't false-positive.
    """
    threshold = float(ctx.params.get("threshold", 0.20))
    last_doc_iso = (
        ctx.params.get("last_sdr_update_at")
        or _supplementary_value(impl, "sdr", "last_updated_at")
        or (
            impl.raw.get("metadata", {}).get("SDR Last Updated")
            if isinstance(impl.raw, dict)
            else None
        )
    )
    if not last_doc_iso:
        return []
    last_doc = _parse_iso(str(last_doc_iso))
    if last_doc is None:
        return []
    components = all_components(impl)
    if not components:
        return []
    drifted: list[str] = []
    for c in components:
        if not c.modified_at:
            continue
        modified = _parse_iso(c.modified_at)
        if modified is None:
            continue
        if modified > last_doc:
            drifted.append(c.id)
    if not drifted:
        return []
    rate = len(drifted) / len(components)
    if rate <= threshold:
        return []
    paragraph = (
        f"{len(drifted)} of {len(components)} components ({pct(len(drifted), len(components))}%) "
        f"have been modified since the SDR was last updated ({last_doc.date()}). "
        "Documentation drift accumulates fast — once analysts learn to ignore "
        "the SDR, you can't easily get them to start trusting it again."
    )
    return [
        _make_finding(
            ctx,
            title=f"{len(drifted)} components modified since last SDR update",
            paragraph=paragraph,
            extra_blocks=[FindingBlock(kind="components", items=sorted(drifted)[:25])],
        )
    ]


def _supplementary_value(impl: Implementation, *keys: str):
    """Walk impl.supplementary_data following keys; return None if any miss."""
    cursor = impl.supplementary_data
    for k in keys:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(k)
        if cursor is None:
            return None
    return cursor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signal_present(impl: Implementation, ctx: RuleContext, *keys: str) -> bool:
    """True when any of the named flags resolves to truthy.

    Param overrides win first (so packs can pin behavior). Then fall back to
    the snapshot's own metadata, which the loader / CI can populate.
    """
    for key in keys:
        if key in ctx.params:
            return bool(ctx.params[key])
    metadata = impl.raw.get("metadata") if isinstance(impl.raw, dict) else None
    if isinstance(metadata, dict):
        for key in keys:
            if metadata.get(key):
                return True
    return False


def _parse_iso(value: str) -> datetime | None:
    candidate = value.strip().rstrip("Z")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


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

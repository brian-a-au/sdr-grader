"""Cross-platform parity matrix for rules claiming `platforms: [cja, aa]`.

A rule that declares both platforms is making a claim: it grades the
same property regardless of whether the snapshot came from AA or CJA.
This test enforces two halves of that contract:

1. **No false positives on clean fixtures.** A rule firing on a clean
   AA snapshot but not a clean CJA snapshot (or vice versa) usually
   means the rule is silently measuring a platform-specific field.

2. **At least one platform's messy fixture exercises the rule.**
   A cross-platform rule whose check function never fires on either
   messy fixture is dead weight or — worse — silently broken on real
   inputs.

The check function is invoked directly (not the full engine) so we can
isolate per-rule behavior even when other rules in the pack would have
suppressed it via category weighting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdr_grader.adapters import aa as aa_adapter
from sdr_grader.adapters import cja as cja_adapter
from sdr_grader.rules.engine import RuleContext
from sdr_grader.rules.registry import get_check
from sdr_grader.rules.rubric import load_rubric

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
STRICT_PACK = PROJECT_ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"

# Cross-platform rules that don't currently fire on either messy fixture.
# This is the Phase 4 (rubric quality pass) backlog: each rule either needs
# a messy fixture that exercises it, or the rule logic is dead and should
# be redesigned or removed. Removing an ID from this set will cause the
# strict "fires on messy" assertion to take effect — that's the proof a
# Phase 4 fix landed.
KNOWN_PHASE4_GAPS: frozenset[str] = frozenset({
    # NAME-001 and NAME-003 were demoted to opt-in (May 2026 audit); they
    # no longer appear in the strict pack so this set drops them.
    "ATTR-003",
    "GOV-002",
    "NAME-002",
    "SCH-001",
    "SCH-004",
    "SCH-005",
    "SEG-004",
    "SEG-006",
})

# Cross-platform rules deliberately calibrated to fire only on extreme
# tenants (near-saturation thresholds). Real-corpus distributions for
# these metrics are so skewed toward "missing" that any threshold below
# saturation would fire on most healthy tenants, defeating the rule.
# Synthetic messy fixtures aren't pushed to ≥95% missing on these
# populations because that would be artificial — production data shows
# that IS the normal state.
INTENTIONALLY_QUIET: frozenset[str] = frozenset({
    "SEG-005",   # threshold 0.95 — see docs/threshold_calibration.md
    "CALC-001",  # threshold 0.95 — see docs/threshold_calibration.md
})


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _impls():
    return {
        "cja_clean": cja_adapter.adapt(_load_json("cja_snapshot_clean.json")),
        "cja_messy": cja_adapter.adapt(_load_json("cja_snapshot_messy.json")),
        "aa_clean": aa_adapter.adapt(_load_json("aa_snapshot_clean.json")),
        "aa_messy": aa_adapter.adapt(_load_json("aa_snapshot_messy.json")),
    }


def _cross_platform_rules():
    rubric = load_rubric(STRICT_PACK)
    return [r for r in rubric.rules if set(r.platforms) >= {"cja", "aa"}]


def _ctx(rule) -> RuleContext:
    return RuleContext(
        rule_id=rule.id,
        rule_name=rule.name,
        severity=rule.severity,
        category=rule.category,
        platforms=rule.platforms,
        params=rule.params,
        rationale=rule.rationale,
        remediation=rule.remediation,
    )


@pytest.fixture(scope="module")
def impls():
    return _impls()


@pytest.mark.parametrize("rule", _cross_platform_rules(), ids=lambda r: r.id)
def test_cross_platform_rule_quiet_on_clean(rule, impls):
    """Cross-platform rules must not fire on clean fixtures of either platform.

    A finding here is the canonical "rule is too tight" signal — the
    threshold or condition is firing on a clean implementation and would
    therefore fire on a typical healthy production tenant. Tune the
    threshold or redesign the check.
    """
    check = get_check(rule.check)
    ctx = _ctx(rule)
    cja_findings = check(impls["cja_clean"], ctx)
    aa_findings = check(impls["aa_clean"], ctx)
    assert cja_findings == [], (
        f"{rule.id} ({rule.check}) fired on clean CJA fixture: "
        f"{[f.title for f in cja_findings]}"
    )
    assert aa_findings == [], (
        f"{rule.id} ({rule.check}) fired on clean AA fixture: "
        f"{[f.title for f in aa_findings]}"
    )


@pytest.mark.parametrize("rule", _cross_platform_rules(), ids=lambda r: r.id)
def test_cross_platform_rule_fires_on_at_least_one_messy(rule, impls):
    """Each cross-platform rule must fire on at least one platform's messy fixture.

    A rule declared as `platforms: [cja, aa]` that never fires on either
    messy fixture is either dead (no real data exercises it) or silently
    broken (it measures a field neither fixture populates). Either is a
    rubric quality issue. Update fixtures or redesign the rule.

    Rules currently in KNOWN_PHASE4_GAPS are tracked as expected failures;
    if one of them starts firing, the test fails XPASS to force the gap
    set to be updated.
    """
    check = get_check(rule.check)
    ctx = _ctx(rule)
    cja_fired = bool(check(impls["cja_messy"], ctx))
    aa_fired = bool(check(impls["aa_messy"], ctx))
    fired = cja_fired or aa_fired

    if rule.id in KNOWN_PHASE4_GAPS:
        assert not fired, (
            f"{rule.id} now fires on a messy fixture — remove it from "
            "KNOWN_PHASE4_GAPS in this test file."
        )
        return

    if rule.id in INTENTIONALLY_QUIET:
        # No assertion either way — calibration says these should fire
        # rarely. If you flip the test to assert it fires, you'll need
        # a fixture pathologically extreme enough to clear the
        # near-saturation threshold, which contradicts the calibration
        # rationale.
        return

    assert fired, (
        f"{rule.id} ({rule.check}) didn't fire on either messy fixture — "
        "rule may be dead, or messy fixtures need to exercise it. "
        "Add to KNOWN_PHASE4_GAPS (gap to close) or INTENTIONALLY_QUIET "
        "(calibrated to near-saturation)."
    )

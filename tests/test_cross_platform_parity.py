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

import copy
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

PURPOSE_BUILT_RAW_TRIGGER_RULES: frozenset[str] = frozenset({
    "ATTR-003",
    "NAME-001",
    "NAME-002",
    "NAME-003",
    "SCH-001",
    "SCH-004",
    "SCH-005",
    "SEG-004",
    "SEG-006",
})

INTENTIONALLY_QUIET: dict[str, str] = {
    "SEG-005": "near-saturation threshold; see docs/threshold_calibration.md",
    "CALC-001": "near-saturation threshold; see docs/threshold_calibration.md",
}


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


def _records(snapshot: dict, platform: str, section: str) -> list[dict]:
    value = snapshot[section]
    if platform == "cja" and isinstance(value, dict):
        key = "metrics" if section == "calculated_metrics" else "segments"
        return value[key]
    return value


def _mutate_raw_trigger(snapshot: dict, platform: str, rule_id: str) -> None:
    dimensions = _records(snapshot, platform, "dimensions")
    metrics = _records(snapshot, platform, "metrics")
    calc_metrics = _records(snapshot, platform, "calculated_metrics")
    segments = _records(snapshot, platform, "segments")

    if rule_id == "SCH-001":
        dimensions[0]["name"] = "Duplicate dimension"
        dimensions[1]["name"] = "Duplicate dimension"
    elif rule_id == "SCH-004":
        metrics[0]["name"] = "Checkout Conversion Rate"
        metrics[0]["type"] = "int"
        metrics[0]["dataType"] = "integer"
    elif rule_id == "SCH-005":
        metrics[0]["tags"] = ["deprecated"]
    elif rule_id == "NAME-001":
        prefixes = ("aa_", "bb_", "cc_")
        for index, dimension in enumerate(dimensions):
            dimension["id"] = f"variables/{prefixes[index % 3]}field{index}"
    elif rule_id == "NAME-002":
        dimensions[0]["id"] = "variables/invalid id"
    elif rule_id == "NAME-003":
        names = (
            lambda index: f"Customer Value {index}",
            lambda index: f"customer_value_{index}",
            lambda index: f"customerValue{index}",
        )
        for index, dimension in enumerate(dimensions):
            dimension["name"] = names[index % 3](index)
    elif rule_id == "ATTR-003":
        if platform == "cja":
            for metric in calc_metrics[:2]:
                metric["metric_references"] = ["metrics/cm_clean_metric_01"]
                metric["segment_references"] = []
            calc_metrics[0]["definition_json"] = json.dumps(
                {"func": "metric", "attribution": "linear"}
            )
            calc_metrics[1]["definition_json"] = json.dumps(
                {"func": "metric", "attribution": "first-touch"}
            )
        else:
            shared_formula = {
                "func": "metric",
                "args": ["metrics/event1"],
            }
            calc_metrics[0]["definition"] = {"formula": copy.deepcopy(shared_formula)}
            calc_metrics[1]["definition"] = {"formula": copy.deepcopy(shared_formula)}
            calc_metrics[0]["attribution"] = "linear"
            calc_metrics[1]["attribution"] = "first-touch"
    elif rule_id == "SEG-004":
        id_key = "segment_id" if platform == "cja" else "id"
        first_id = segments[0][id_key]
        second_id = segments[1][id_key]
        if platform == "cja":
            segments[0]["other_segment_references"] = [second_id]
            segments[1]["other_segment_references"] = [first_id]
        else:
            segments[0]["definition"] = {"args": [second_id]}
            segments[1]["definition"] = {"args": [first_id]}
    elif rule_id == "SEG-006":
        if platform == "cja":
            segments[1]["definition_json"] = segments[0]["definition_json"]
        else:
            segments[1]["definition"] = copy.deepcopy(segments[0]["definition"])
    else:
        raise AssertionError(f"missing raw trigger mutation for {rule_id}")


def test_bundled_pack_2_removes_inert_and_raw_count_rules():
    for pack_name in ("strict", "pragmatic"):
        rubric = load_rubric(STRICT_PACK.parent / pack_name)
        ids = {rule.id for rule in rubric.rules}

        assert rubric.version == "2.0"
        assert len(rubric.rules) == 27
        assert ids.isdisjoint({"GOV-002", "GOV-007", "GOV-008"})


@pytest.mark.parametrize(
    "check_name",
    [
        "cardinality_concerns",
        "calc_metric_shared_unapproved",
        "segment_shared_unapproved",
    ],
)
def test_raw_count_checks_are_not_registered(check_name):
    load_rubric(STRICT_PACK)

    with pytest.raises(KeyError, match="no check function registered"):
        get_check(check_name)


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

    Rules whose shared messy fixture does not naturally exercise the premise
    have separate purpose-built raw trigger proofs below.
    """
    if rule.id in PURPOSE_BUILT_RAW_TRIGGER_RULES:
        return

    check = get_check(rule.check)
    ctx = _ctx(rule)
    cja_fired = bool(check(impls["cja_messy"], ctx))
    aa_fired = bool(check(impls["aa_messy"], ctx))
    fired = cja_fired or aa_fired

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
        "Add a purpose-built raw trigger proof or document it in "
        "INTENTIONALLY_QUIET with a calibration rationale."
    )


@pytest.mark.parametrize(
    "rule_id",
    sorted(PURPOSE_BUILT_RAW_TRIGGER_RULES),
)
@pytest.mark.parametrize(
    ("platform", "fixture_name", "adapter"),
    [
        ("cja", "cja_snapshot_clean.json", cja_adapter),
        ("aa", "aa_snapshot_clean.json", aa_adapter),
    ],
)
def test_cross_platform_rule_has_raw_trigger_proof(
    rule_id,
    platform,
    fixture_name,
    adapter,
):
    snapshot = copy.deepcopy(_load_json(fixture_name))
    _mutate_raw_trigger(snapshot, platform, rule_id)
    implementation = adapter.adapt(snapshot)
    rule = next(rule for rule in _cross_platform_rules() if rule.id == rule_id)

    findings = get_check(rule.check)(implementation, _ctx(rule))

    assert [finding.id for finding in findings] == [rule_id]

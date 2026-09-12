"""Shared reference policy preserves uncertainty and per-rule assessment."""

from dataclasses import replace
from pathlib import Path

import pytest

from _rule_test_helpers import calc, component, ctx, impl, segment
from sdr_grader.core.models import ReferenceClassification
from sdr_grader.rules.checks.calc_metrics import check_calc_formula_broken_refs
from sdr_grader.rules.checks.schema_hygiene import check_broken_references
from sdr_grader.rules.engine import resolve_effective_rules, resolve_rule_inventory, run_rules
from sdr_grader.rules.rubric import load_rubric

FLAG = "exclude_unresolved_calculated_metric_segments"
CHECKS = [check_broken_references, check_calc_formula_broken_refs]
PACKS = Path(__file__).resolve().parents[1] / "src/sdr_grader/rules/packs"


def typed_calc(refs=("missing-segment",)):
    cm = calc("cm", references=list(refs))
    cm.reference_classifications = {
        "missing-segment": ReferenceClassification(kinds=frozenset({"segment"}))
    }
    return cm


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("check", CHECKS)
def test_direct_checks_exclude_only_typed_missing_segments(platform, check):
    cm = typed_calc(["missing-segment", "missing-metric", "resolved"])
    snapshot = impl(platform=platform, calc=[cm], metrics=[component(1, cid="resolved")])
    before = list(cm.references)
    findings = check(snapshot, ctx("CUSTOM", **{FLAG: True}))
    assert len(findings) == 1
    items = [item for block in findings[0].body for item in (block.items or [])]
    assert len(items) == 1
    assert "missing-metric" in items[0]
    assert "missing-segment" not in items[0]
    assert cm.references == before


@pytest.mark.parametrize("flag", [None, False])
@pytest.mark.parametrize("check", CHECKS)
def test_old_policy_and_default_metadata_keep_failures(flag, check):
    params = {} if flag is None else {FLAG: flag}
    assert check(impl(calc=[typed_calc()]), ctx("CUSTOM", **params))
    assert check(
        impl(calc=[calc("legacy", references=["missing-segment"])]), ctx("CUSTOM", **{FLAG: True})
    )


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("extra", [None, "resolved", "missing-metric"])
def test_effective_inventory_and_runner_agree(pack, platform, extra):
    rubric = load_rubric(PACKS / pack)
    rules = [
        replace(rule, id="CUSTOM-" + rule.id, params={FLAG: True})
        for rule in rubric.rules
        if rule.id in {"SCH-002", "CALC-002"}
    ]
    rubric = replace(rubric, rules=rules)
    refs = ["missing-segment"] + ([extra] if extra else [])
    snapshot = impl(
        platform=platform, calc=[typed_calc(refs)], metrics=[component(1, cid="resolved")]
    )
    inventory = resolve_effective_rules(snapshot, rubric)
    assert len(inventory) == (0 if extra is None else 2)
    assert len(run_rules(snapshot, rubric)) == (2 if extra == "missing-metric" else 0)
    assert resolve_rule_inventory(snapshot, rubric).configured_rules == tuple(rules)
    assert (
        resolve_rule_inventory(
            snapshot, rubric, excluded_rule_ids=[r.id for r in rules]
        ).configured_rules
        == ()
    )


def test_segment_consumers_duplicates_and_conflicts_remain_scoring():
    snapshot = impl(calc=[typed_calc()], segments=[segment("s", references=["missing-segment"])])
    findings = check_broken_references(snapshot, ctx("SCH", **{FLAG: True}))
    assert [item for block in findings[0].body for item in (block.items or [])] == [
        "segment s -> missing missing-segment"
    ]
    for classification in [
        ReferenceClassification(frozenset({"segment", "metric"})),
        ReferenceClassification(frozenset({"segment"}), frozenset({"unknown"})),
    ]:
        cm = typed_calc()
        cm.reference_classifications["missing-segment"] = classification
        assert check_calc_formula_broken_refs(impl(calc=[cm]), ctx("CALC", **{FLAG: True}))
    assert check_calc_formula_broken_refs(
        impl(calc=[typed_calc(), typed_calc()]), ctx("CALC", **{FLAG: True})
    )


def test_partition_preserves_candidates_and_existing_known_union():
    from sdr_grader.core.reference_policy import assess_references

    cm = typed_calc(
        [
            "missing-segment",
            "missing-segment",
            "metric",
            "dimension",
            "derived",
            "segment",
            "cm",
            "alias",
            "unknown",
        ]
    )
    snapshot = impl(
        calc=[cm],
        metrics=[component(1, cid="metric")],
        dimensions=[component(2, cid="dimension")],
        derived=[component(3, cid="derived")],
        segments=[segment("segment")],
    )
    snapshot.available_reference_ids.add("alias")
    assessment = assess_references(
        snapshot, check_name="calc_formula_broken_refs", params={FLAG: True}
    )
    assert [ref.target_id for ref in assessment.excluded] == ["missing-segment"] * 2
    assert [ref.target_id for ref in assessment.resolved] == [
        "metric",
        "dimension",
        "derived",
        "segment",
        "cm",
        "alias",
    ]
    assert [ref.target_id for ref in assessment.unresolved_scoring] == ["unknown"]
    assert not assessment.not_assessed
    snapshot.available_reference_ids.add("missing-segment")
    assert not assess_references(
        snapshot, check_name="calc_formula_broken_refs", params={FLAG: True}
    ).excluded


def test_no_candidates_and_platform_exclusion_keep_existing_behavior():
    rubric = load_rubric(PACKS / "strict")
    rule = replace(
        next(r for r in rubric.rules if r.id == "CALC-002"), params={FLAG: True}, platforms=["aa"]
    )
    rubric = replace(rubric, rules=[rule])
    assert resolve_effective_rules(impl(platform="aa"), rubric) == (rule,)
    assert (
        resolve_rule_inventory(impl(platform="cja", calc=[typed_calc()]), rubric).configured_rules
        == ()
    )


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize(
    "refs,expected_count,expected_failures",
    [
        ([], 2, 0),
        (["missing-segment"], 0, 0),
        (["missing-segment", "resolved"], 2, 0),
        (["missing-segment", "missing-metric"], 2, 2),
    ],
)
def test_assessment_denominators_and_full_mixed_penalties(
    pack, platform, refs, expected_count, expected_failures
):
    from sdr_grader.core.grade_calc import compute_grade

    rubric = load_rubric(PACKS / pack)
    rules = [
        replace(r, params={FLAG: True}) for r in rubric.rules if r.id in {"SCH-002", "CALC-002"}
    ]
    rubric = replace(rubric, rules=rules)
    snapshot = impl(
        platform=platform, calc=[typed_calc(refs)], metrics=[component(1, cid="resolved")]
    )
    inventory = resolve_effective_rules(snapshot, rubric)
    findings = run_rules(snapshot, rubric, rule_inventory=inventory)
    result = compute_grade(rubric, findings, rule_inventory=inventory)
    assert sum(c.rules_total for c in result.categories) == expected_count
    assert sum(c.rules_failed for c in result.categories) == expected_failures
    denominator = sum(rubric.severity_weights[r.severity] for r in inventory)
    failure_weight = sum(
        rubric.severity_weights[r.severity] for r in inventory if r.id in {f.id for f in findings}
    )
    original_weight = sum(rubric.severity_weights[r.severity] for r in rules)
    assert denominator == (original_weight if expected_count else 0)
    assert failure_weight == (original_weight if expected_failures else 0)
    for category in result.categories:
        assert category.pct == (0 if expected_failures and category.rules_total else 100)

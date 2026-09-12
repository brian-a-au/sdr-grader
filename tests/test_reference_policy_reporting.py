"""Schema-preserving unverified diagnostics and assessment disclosures."""

from dataclasses import replace

import pytest

from _rule_test_helpers import component, impl
from sdr_grader.core.grader import grade
from sdr_grader.core.models import ReferenceClassification
from sdr_grader.render import cap_component_items, render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.rules.suppression import SuppressedRule, Suppression
from test_reference_grading_policy import FLAG, PACKS, typed_calc


def policy_rubric(pack="strict"):
    rubric = load_rubric(PACKS / pack)
    return replace(
        rubric,
        rules=[
            replace(r, params={FLAG: True}) for r in rubric.rules if r.id in {"SCH-002", "CALC-002"}
        ],
    )


def diagnostics(report):
    return [str(p) for p in report.methodology.paragraphs if "Unverified reference:" in p]


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
@pytest.mark.parametrize("extra", [None, "resolved", "missing-metric"])
def test_report_assessment_and_deduplicated_diagnostic(platform, pack, extra):
    refs = ["missing-segment"] + ([extra] if extra else [])
    snapshot = impl(
        platform=platform, calc=[typed_calc(refs)], metrics=[component(1, cid="resolved")]
    )
    report = grade(snapshot, policy_rubric(pack))
    assert diagnostics(report) == [
        "Unverified reference: calculated metric cm → segment missing-segment. "
        "Unresolved in this snapshot; excluded from grading by CALC-002, SCH-002."
    ]
    assert len(report.findings) == (2 if extra == "missing-metric" else 0)
    assert len(report.remediations) == (2 if extra == "missing-metric" else 0)
    assert len(report.methodology.skipped) == (2 if extra is None else 0)
    if extra is None:
        assert str(report.tldr_html).startswith("No scoring rules were assessed")
        assert report.overall_pct == 100
    for finding in report.findings:
        items = [item for block in finding.body for item in (block.items or [])]
        assert len(items) == 1 and "missing-metric" in items[0]
    text = " ".join(map(str, report.methodology.paragraphs))
    assert "invalid references in this category are also unscored" in text
    assert "arithmetic default" in text
    assert "arithmetic default" in report.tldr_html
    assert report.components_evaluated == 2


@pytest.mark.parametrize("suppressed", [[], ["SCH-002"], ["CALC-002", "SCH-002"]])
def test_full_suppression_limits_diagnostic_associations(suppressed):
    suppression = Suppression(suppressed=[SuppressedRule(r, "User choice") for r in suppressed])
    report = grade(impl(calc=[typed_calc()]), policy_rubric(), suppression)
    remaining = sorted({"SCH-002", "CALC-002"} - set(suppressed))
    assert len(diagnostics(report)) == bool(remaining)
    if remaining:
        assert diagnostics(report)[0].endswith(", ".join(remaining) + ".")
    policy_skips = [s for s in report.methodology.skipped if "Not assessed:" in s.reason]
    assert [s.ids[0] for s in policy_skips] == remaining


def test_finding_suppression_does_not_erase_policy_diagnostic():
    snapshot = impl(calc=[typed_calc(["missing-segment", "missing-metric"])])
    report = grade(
        snapshot,
        policy_rubric(),
        Suppression(suppressed=[SuppressedRule("CALC-002", "User choice", components=["cm"])]),
    )
    assert len(diagnostics(report)) == 1
    assert "CALC-002, SCH-002" in diagnostics(report)[0]


def test_custom_ids_zero_weight_and_disabled_policy():
    rubric = policy_rubric()
    rules = [replace(r, id="X-" + r.id) for r in rubric.rules]
    weights = dict(rubric.category_weights)
    weights["schema_hygiene"] = 0
    report = grade(
        impl(calc=[typed_calc()]), replace(rubric, rules=rules, category_weights=weights)
    )
    assert diagnostics(report)[0].endswith("X-CALC-002, X-SCH-002.")
    report = grade(
        impl(calc=[typed_calc()]),
        replace(rubric, rules=[replace(r, params={FLAG: False}) for r in rules]),
    )
    assert diagnostics(report) == []
    assert len(report.findings) == 2


def test_many_diagnostics_are_complete_escaped_and_deterministic():
    cm = typed_calc()
    cm.id = '<script>alert("consumer")</script>'
    cm.references = [f'<img src=x onerror="{i:03d}">' for i in range(61)]
    cm.reference_classifications = {
        ref: ReferenceClassification(kinds=frozenset({"segment"})) for ref in cm.references
    }
    snapshot = impl(calc=[cm])
    rubric = policy_rubric()
    report = grade(snapshot, rubric)
    assert len(diagnostics(report)) == 61
    html = render(cap_component_items(report))
    assert html.count("Unverified reference:") == 61
    assert '<script>alert("consumer")</script>' not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html
    machine = report_to_dict(report)
    assert machine["schema_version"] == 1
    assert set(machine["methodology"]) == {"paragraphs", "skipped"}
    assert (
        len([p for p in machine["methodology"]["paragraphs"] if "Unverified reference:" in p]) == 61
    )
    assert machine == report_to_dict(grade(snapshot, rubric))
    assert html == render(cap_component_items(grade(snapshot, rubric)))
    assert machine["findings"] == machine["remediations"] == []

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from sdr_grader.adapters.aa import adapt
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.grade_calc import compute_grade
from sdr_grader.core.grader import grade
from sdr_grader.render import render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.engine import RuleContext, resolve_rule_inventory, run_rules
from sdr_grader.rules.registry import get_check
from sdr_grader.rules.rubric import load_rubric

PACK = Path(__file__).parents[1] / "src/sdr_grader/rules/packs/aa-admin"


def test_missing_evidence_not_passed():
    impl = adapt({"report_suite": {"rsid": "suite"}, "dimensions": [], "metrics": []})
    report = grade(impl, load_rubric(PACK))
    assert len(report.methodology.skipped) == 4
    assert "No scoring rules were assessed" in str(report.tldr_html)


FIXTURES = Path(__file__).parent / "fixtures/aa_admin"


def inputs():
    return (
        json.loads((FIXTURES / "snapshot.json").read_text()),
        json.loads((FIXTURES / "evidence.json").read_text()),
    )


def implementation(snapshot=None, evidence=None):
    base, extra = inputs()
    impl = adapt(base if snapshot is None else snapshot)
    impl.supplementary_data["aa_admin"] = extra if evidence is None else evidence
    return impl


def test_full_chain_pass_and_determinism():
    impl = implementation()
    rubric = load_rubric(PACK)
    report = grade(impl, rubric)
    assert report.findings == []
    assert report.methodology.skipped == []
    assert report.overall_pct == 100
    assert "AA-004 assessed only declared targets: variables/evar1" in render(report)
    assert render(report) == render(grade(impl, rubric))
    assert len(resolve_rule_inventory(impl, rubric).effective_rules) == 4


@pytest.mark.parametrize(
    ("kind", "field", "value", "rule"),
    [
        ("evars", "expiration_days", 90, "AA-001"),
        ("events", "event_type", "currency", "AA-002"),
        ("events", "serialization", "always", "AA-003"),
        ("evars", "binding_events", [], "AA-004"),
    ],
)
def test_each_rule_fails(kind, field, value, rule):
    snapshot, evidence = inputs()
    evidence["expectations"][kind][0][field] = value
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert [finding.id for finding in report.findings] == [rule]
    assert report.overall_pct == 75


@pytest.mark.parametrize("location", ["top", "extra", "both"])
def test_api_mapping(location):
    snapshot, evidence = inputs()
    record = snapshot["dimensions"][0]
    settings = record["extra"]
    if location != "extra":
        record.update(settings)
    if location == "top":
        del record["extra"]
    assert not grade(implementation(snapshot, evidence), load_rubric(PACK)).findings


def test_supplement_can_supply_missing_api_expansions():
    snapshot, evidence = inputs()
    snapshot["dimensions"][0].pop("extra")
    evidence["observations"]["evars"] = copy.deepcopy(evidence["expectations"]["evars"])
    assert not grade(implementation(snapshot, evidence), load_rubric(PACK)).methodology.skipped


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=2),
        lambda d: d.update(platform="cja"),
        lambda d: d.update(report_suite_id="wrong"),
        lambda d: d.update(captured_at="bad"),
        lambda d: d.update(source=""),
        lambda d: d.update(unrecognized=True),
        lambda d: d.pop("observations"),
        lambda d: d.update(observations=[]),
        lambda d: d["observations"].update(events={}),
        lambda d: d["observations"]["events"].append(d["observations"]["events"][0]),
        lambda d: d["observations"]["events"].append([]),
        lambda d: d["observations"]["events"][0].update(id=3),
        lambda d: d["observations"]["events"][0].update(id="metrics/revenue"),
        lambda d: d["observations"]["events"][0].update(event_type={}),
        lambda d: d["expectations"]["events"][0].update(event_type="unknown"),
        lambda d: d["observations"]["events"][0].update(type="counter"),
        lambda d: d["expectations"]["evars"][0].update(expiration_days=True),
        lambda d: d["expectations"]["evars"][0].update(expiration_days=0),
        lambda d: d["expectations"]["evars"][0].update(binding_events=None),
        lambda d: d["expectations"]["evars"][0].update(binding_events=[{}]),
        lambda d: d["expectations"]["evars"][0].update(binding_events=["event1"]),
        lambda d: d["expectations"]["evars"][0].update(binding_events=["metrics/event1"] * 2),
    ],
)
def test_invalid_evidence_controlled(change):
    snapshot, evidence = inputs()
    change(evidence)
    with pytest.raises(InvalidSnapshotError, match="aa_admin: malformed") as exc:
        grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert "wrong" not in str(exc.value)


@pytest.mark.parametrize("source", ["api", "supplement", "duplicate"])
def test_conflicts_rejected(source):
    snapshot, evidence = inputs()
    if source == "api":
        snapshot["dimensions"][0]["allocationType"] = "linear"
    elif source == "supplement":
        evidence["observations"]["evars"] = [{"id": "variables/evar1", "allocation": "linear"}]
    else:
        snapshot["dimensions"].append(copy.deepcopy(snapshot["dimensions"][0]))
    with pytest.raises(InvalidSnapshotError):
        grade(implementation(snapshot, evidence), load_rubric(PACK))


@pytest.mark.parametrize("mode", ["absent", "partial", "unknown", "no_expectations"])
def test_rule_entirely_excluded(mode):
    snapshot, evidence = inputs()
    if mode == "absent":
        del evidence["observations"]["events"][0]["serialization"]
    elif mode == "partial":
        evidence["expectations"]["events"].append(
            {"id": "metrics/event2", "serialization": "always"}
        )
    elif mode == "unknown":
        evidence["observations"]["events"][0]["serialization"] = "unsupported"
    else:
        del evidence["expectations"]["events"][0]["serialization"]
    evidence["observations"]["events"][0]["event_type"] = "numeric"
    impl = implementation(snapshot, evidence)
    rubric = load_rubric(PACK)
    resolution = resolve_rule_inventory(impl, rubric)
    assert [r.id for r in resolution.effective_rules] == ["AA-001", "AA-002", "AA-004"]
    findings = run_rules(impl, rubric)
    score = compute_grade(rubric, findings, rule_inventory=resolution.effective_rules)
    assert score.categories[0].rules_total == 3
    assert score.overall_pct == 67
    report = grade(impl, rubric)
    assert report.methodology.skipped[0].ids == ["AA-003"]
    assert report.overall_pct == 67


def test_empty_binding_is_observed_absent_is_not():
    snapshot, evidence = inputs()
    snapshot["dimensions"][0]["extra"]["bindingEvents"] = []
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert [f.id for f in report.findings] == ["AA-004"]
    del snapshot["dimensions"][0]["extra"]["bindingEvents"]
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert report.methodology.skipped[0].ids == ["AA-004"]


def test_product_syntax_needs_no_binding_and_syntax_mismatch_fails():
    snapshot, evidence = inputs()
    evidence["expectations"]["evars"][0]["merchandising_syntax"] = "product"
    del evidence["expectations"]["evars"][0]["binding_events"]
    assert [
        f.id for f in grade(implementation(snapshot, evidence), load_rubric(PACK)).findings
    ] == ["AA-004"]
    snapshot["dimensions"][0]["extra"]["merchandisingSyntax"] = "product"
    del snapshot["dimensions"][0]["extra"]["bindingEvents"]
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert not report.findings and not report.methodology.skipped


def test_missing_days_and_unknown_api_settings_excluded():
    snapshot, evidence = inputs()
    del snapshot["dimensions"][0]["extra"]["expirationCustomDays"]
    snapshot["dimensions"][0]["extra"]["allocationType"] = "new_api_token"
    snapshot["dimensions"].append({"id": "variables/prop1"})
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert [s.ids for s in report.methodology.skipped] == [["AA-001"], ["AA-004"]]


def test_no_declared_targets_and_null_document():
    snapshot, evidence = inputs()
    evidence["expectations"] = {}
    assert (
        len(grade(implementation(snapshot, evidence), load_rubric(PACK)).methodology.skipped) == 4
    )
    impl = implementation()
    impl.supplementary_data["aa_admin"] = None
    with pytest.raises(InvalidSnapshotError):
        grade(impl, load_rubric(PACK))


@pytest.mark.parametrize("name", ["strict", "pragmatic"])
def test_default_packs_validate_aa_input_and_keep_baseline_without_evidence(name):
    impl = implementation()
    impl.supplementary_data["aa_admin"] = "malformed"
    rubric = load_rubric(PACK.parent / name)
    with pytest.raises(InvalidSnapshotError, match="aa_admin: malformed"):
        grade(impl, rubric)

    impl.supplementary_data.clear()
    report = grade(impl, rubric)
    previous = replace(
        rubric,
        rules=[rule for rule in rubric.rules if not rule.id.startswith("AA-")],
    )
    previous_report = grade(impl, previous)
    assert report.findings == previous_report.findings
    assert report.overall_pct == previous_report.overall_pct
    assert report.grade == previous_report.grade
    assert {rule_id for item in report.methodology.skipped for rule_id in item.ids} == {
        "AA-001", "AA-002", "AA-003", "AA-004"
    }


def test_standalone_pack_ignores_aa_input_for_cja():
    impl = implementation()
    impl.supplementary_data["aa_admin"] = "malformed"
    impl.platform = "cja"
    assert not resolve_rule_inventory(impl, load_rubric(PACK)).effective_rules
    assert not grade(impl, load_rubric(PACK)).findings


@pytest.mark.parametrize("name", ["strict", "pragmatic"])
def test_default_packs_execute_complete_aa_evidence_and_grade_findings(name):
    snapshot, evidence = inputs()
    evidence["expectations"]["evars"][0].update(
        allocation="linear", expiration_days=90, binding_events=[]
    )
    evidence["expectations"]["events"][0].update(
        event_type="currency", serialization="always"
    )
    impl = implementation(snapshot, evidence)
    rubric = load_rubric(PACK.parent / name)
    assert len(resolve_rule_inventory(impl, rubric).effective_rules) == 27
    report = grade(impl, rubric)
    aa_findings = {finding.id for finding in report.findings if finding.id.startswith("AA-")}
    assert aa_findings == {"AA-001", "AA-002", "AA-003", "AA-004"}
    assert report.overall_pct < 100
    assert not ({"AA-001", "AA-002", "AA-003", "AA-004"} & {
        rule_id for item in report.methodology.skipped for rule_id in item.ids
    })


@pytest.mark.parametrize("name", ["strict", "pragmatic"])
def test_default_packs_exclude_and_disclose_partial_aa_evidence(name):
    snapshot, evidence = inputs()
    del evidence["observations"]["events"][0]["serialization"]
    report = grade(implementation(snapshot, evidence), load_rubric(PACK.parent / name))
    skipped = {
        rule_id: item.reason
        for item in report.methodology.skipped
        for rule_id in item.ids
    }
    assert "AA-003" in skipped
    assert "Not assessed" in skipped["AA-003"]
    assert "AA-003" not in {finding.id for finding in report.findings}


def test_direct_checks_and_supplied_inventory():
    rubric = load_rubric(PACK)
    impl = implementation()
    assert not run_rules(impl, rubric, rule_inventory=rubric.rules)
    ctx = RuleContext("AA-002", "Event type", "high", "aa_administration", ["aa"])
    check = get_check("aa_event_type")
    assert not check(impl, ctx)
    impl.supplementary_data.clear()
    assert not check(impl, ctx)
    impl.platform = "cja"
    assert not check(impl, ctx)


def test_cli_real_extra_file_and_escaping(tmp_path):
    snapshot, evidence = inputs()
    snapshot["report_suite"]["name"] = "<script>alert(1)</script>"
    source = tmp_path / "snapshot.json"
    extra = tmp_path / "evidence.json"
    output = tmp_path / "grade.html"
    source.write_text(json.dumps(snapshot))
    extra.write_text(json.dumps(evidence))
    assert (
        main(
            [
                str(source),
                "--pack",
                "aa-admin",
                "--extra-input",
                f"aa_admin={extra}",
                "--output",
                str(output),
                "--quiet",
            ]
        )
        == 0
    )
    html = output.read_text()
    assert "AA-004 assessed only declared targets" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    extra.write_text(json.dumps({**evidence, "expectations": {}}))
    assert (
        main(
            [
                str(source),
                "--pack",
                "aa-admin",
                "--extra-input",
                f"aa_admin={extra}",
                "--output",
                str(output),
                "--quiet",
            ]
        )
        == 0
    )
    assert "Not assessed: No declared targets." in output.read_text()


def test_json_skipped_and_normalized_shape_validation():
    impl = implementation()
    impl.supplementary_data.clear()
    document = report_to_dict(grade(impl, load_rubric(PACK)))
    assert len(document["methodology"]["skipped"]) == 4
    assert "Not assessed" in document["methodology"]["skipped"][0]["reason"]
    impl = implementation()
    impl.dimensions[0].platform_specific["aa_admin_sources"] = [{"unknown": "bad"}]
    with pytest.raises(InvalidSnapshotError):
        grade(impl, load_rubric(PACK))


def test_expiration_change_and_partial_expectation():
    snapshot, evidence = inputs()
    evidence["expectations"]["evars"][0]["expiration"] = "visit"
    del evidence["expectations"]["evars"][0]["expiration_days"]
    assert [
        f.id for f in grade(implementation(snapshot, evidence), load_rubric(PACK)).findings
    ] == ["AA-001"]
    del evidence["expectations"]["evars"][0]["allocation"]
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert [item.ids for item in report.methodology.skipped] == [["AA-001"], ["AA-004"]]


def test_api_null_fields_are_unavailable_not_malformed():
    """Adobe's documented non-merchandising dimension has explicit nulls."""
    snapshot, evidence = inputs()
    snapshot["dimensions"][0]["extra"] = {
        "allocationType": "linear",
        "expirationType": "visit",
        "expirationCustomDays": None,
        "bindingEvents": [],
        "merchandisingSyntax": None,
    }
    evidence["expectations"]["evars"] = [
        {
            "id": "variables/evar1",
            "allocation": "linear",
            "expiration": "visit",
            "merchandising_syntax": "conversion_variable",
            "binding_events": [],
        }
    ]
    impl = implementation(snapshot, evidence)
    resolution = resolve_rule_inventory(impl, load_rubric(PACK))
    assert [rule.id for rule in resolution.effective_rules] == ["AA-001", "AA-002", "AA-003"]
    report = grade(impl, load_rubric(PACK))
    assert not report.findings
    assert [item.ids for item in report.methodology.skipped] == [["AA-004"]]


@pytest.mark.parametrize("field", ["allocationType", "expirationType", "merchandisingSyntax"])
@pytest.mark.parametrize("value", [None, "unsupported_api_value"])
def test_required_api_null_or_unknown_never_passes(field, value):
    snapshot, evidence = inputs()
    snapshot["dimensions"][0]["extra"][field] = value
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    excluded = {rid for item in report.methodology.skipped for rid in item.ids}
    assert ("AA-004" if field == "merchandisingSyntax" else "AA-001") in excluded


def test_api_null_source_does_not_override_other_source():
    snapshot, evidence = inputs()
    snapshot["dimensions"][0]["allocationType"] = None
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert not report.findings and not report.methodology.skipped
    evidence["observations"]["evars"] = [{"id": "variables/evar1", "allocation": "linear"}]
    with pytest.raises(InvalidSnapshotError):
        grade(implementation(snapshot, evidence), load_rubric(PACK))


def test_supplementary_null_settings_remain_malformed():
    snapshot, evidence = inputs()
    evidence["observations"]["evars"] = [{"id": "variables/evar1", "merchandising_syntax": None}]
    with pytest.raises(InvalidSnapshotError):
        grade(implementation(snapshot, evidence), load_rubric(PACK))


@pytest.mark.parametrize("identifier", ["metrics/", "metrics/ ", "metrics/\t", "metrics/event 1"])
@pytest.mark.parametrize("source", ["api", "supplement", "expectation"])
def test_binding_metric_id_requires_complete_non_whitespace_id(identifier, source):
    snapshot, evidence = inputs()
    if source == "expectation":
        evidence["expectations"]["evars"][0]["binding_events"] = [identifier]
    elif source == "api":
        snapshot["dimensions"][0]["extra"]["bindingEvents"] = [identifier]
    else:
        del snapshot["dimensions"][0]["extra"]["bindingEvents"]
        evidence["observations"]["evars"] = [
            {"id": "variables/evar1", "binding_events": [identifier]}
        ]
    with pytest.raises(InvalidSnapshotError):
        grade(implementation(snapshot, evidence), load_rubric(PACK))


def test_binding_metric_ids_preserve_opaque_suffixes():
    snapshot, evidence = inputs()
    identifiers = ["metrics/orders", "metrics/vendor:opaque-id_42"]
    snapshot["dimensions"][0]["extra"]["bindingEvents"] = identifiers
    evidence["expectations"]["evars"][0]["binding_events"] = list(reversed(identifiers))
    report = grade(implementation(snapshot, evidence), load_rubric(PACK))
    assert not report.findings and not report.methodology.skipped

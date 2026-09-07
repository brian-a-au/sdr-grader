"""Synthetic export-to-report reproductions of the v1.2.7 correctness audit."""

import json
from copy import deepcopy
from html import escape

import pytest

from _rule_test_helpers import ctx
from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt
from sdr_grader.cli.main import BUNDLED_PACKS_DIR, main
from sdr_grader.core.grader import grade
from sdr_grader.render import render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.checks.calc_metrics import check_calc_identical_formula_text
from sdr_grader.rules.checks.schema_hygiene import (
    check_deprecated_components,
    check_derived_field_broken_refs,
    check_derived_field_cycles,
)
from sdr_grader.rules.checks.segments import check_duplicate_segments
from sdr_grader.rules.rubric import load_rubric


def cja_snapshot(**sections):
    return {
        "metadata": {"Data View ID": "dv_synthetic"},
        "dimensions": [],
        "metrics": [],
        **sections,
    }


@pytest.mark.parametrize("platform", ["cja", "aa"])
@pytest.mark.parametrize("definition", [None, {}, "", "not JSON", []])
def test_unavailable_segment_definitions_are_not_duplicate_evidence(platform, definition):
    key = "definition_json" if platform == "cja" else "definition"
    segments = [{"id": sid, key: definition} for sid in ("s_a", "s_b")]
    snapshot = cja_snapshot(segments=segments)
    adapter = adapt
    if platform == "aa":
        snapshot = {"report_suite": {"rsid": "synthetic"}, "metrics": [],
                    "dimensions": [], "segments": segments}
        adapter = adapt_aa
    implementation = adapter(snapshot)
    assert check_duplicate_segments(implementation, ctx("SEG-006")) == []
    # An unavailable third definition must not hide an observed duplicate pair.
    observed = {"func": "container", "context": "hits"}
    snapshot["segments"].extend([
        {"id": "s_c", key: observed}, {"id": "s_d", key: deepcopy(observed)}
    ])
    finding = check_duplicate_segments(adapter(snapshot), ctx("SEG-006"))[0]
    assert finding.body[1].items == ["s_c, s_d  (2 segments share definition)"]


@pytest.mark.parametrize("missing", [True, False])
def test_metric_dimension_collision_is_not_a_derived_field_cycle(missing):
    snapshot = cja_snapshot(
        metrics=[] if missing else [{"id": "metrics/orders"}],
        derived_fields=[{"id": "variables/orders", "component_references": ["metrics/orders"]}],
    )
    implementation = adapt(snapshot)
    assert check_derived_field_cycles(implementation, ctx("SCH-008")) == []
    unresolved = check_derived_field_broken_refs(implementation, ctx("SCH-009"))
    assert bool(unresolved) == missing
    if missing:
        assert unresolved[0].body[1].items == ["variables/orders -> missing metrics/orders"]


@pytest.mark.parametrize("namespace", ["variables", "dimensions"])
def test_real_derived_field_cycles_resolve_dimension_aliases(namespace):
    implementation = adapt(cja_snapshot(derived_fields=[
        {"id": "variables/a", "component_references": [f"{namespace}/b"]},
        {"id": "variables/b", "component_references": [f"{namespace}/a"]},
    ]))
    assert check_derived_field_broken_refs(implementation, ctx("SCH-009")) == []
    findings = check_derived_field_cycles(implementation, ctx("SCH-008"))
    assert findings[0].body[1].items == ["variables/a, variables/b"]


def test_alias_resolution_preserves_path_and_exact_ids():
    implementation = adapt(cja_snapshot(
        dimensions=[{"id": "variables/group/a"}, {"id": "variables/a"},
                    {"id": "dimensions/a"}],
        derived_fields=[{"id": "variables/df", "component_references": [
            "dimensions/group/a", "metrics/group/a", "another/group/a", "a",
        ]}],
    ))
    assert implementation.reference_aliases == {
        "dimensions/group/a": "variables/group/a", "dimensions/df": "variables/df"
    }
    finding = check_derived_field_broken_refs(implementation, ctx("SCH-009"))[0]
    assert finding.body[1].items == [
        "variables/df -> missing metrics/group/a",
        "variables/df -> missing another/group/a",
        "variables/df -> missing a",
    ]


def test_alias_consumers_still_identify_deprecated_components():
    implementation = adapt(cja_snapshot(
        dimensions=[{"id": "variables/channel", "tags": ["deprecated"]}],
        segments=[{"id": "s1", "dimension_references": ["dimensions/channel"]}],
    ))
    finding = check_deprecated_components(implementation, ctx("SCH-005"))[0]
    assert finding.body[1].items == ["variables/channel"]


def test_abbreviated_summaries_do_not_override_different_known_formulas():
    metrics = [{"id": f"cm_{number}", "formula_summary": "Ratio calculation",
                "definition_json": {"formula": {"func": "divide", "col1": number, "col2": 10}}}
               for number in (1, 2)]
    snapshot = cja_snapshot(calculated_metrics=metrics)
    assert check_calc_identical_formula_text(adapt(snapshot), ctx("CALC-015")) == []
    duplicate = deepcopy(metrics[0])
    duplicate["id"] = "cm_duplicate"
    metrics.append(duplicate)
    finding = check_calc_identical_formula_text(adapt(snapshot), ctx("CALC-015"))[0]
    assert finding.body[1].items == ["'Ratio calculation': cm_1, cm_duplicate"]


def test_two_duplicate_pairs_can_share_one_summary_text():
    metrics = [{"id": f"cm_{index}", "formula_summary": "Ratio calculation",
                "definition_json": {"formula": {"func": "divide", "col1": value, "col2": 10}}}
               for index, value in enumerate((1, 1, 2, 2))]
    finding = check_calc_identical_formula_text(
        adapt(cja_snapshot(calculated_metrics=metrics)), ctx("CALC-015")
    )[0]
    assert finding.title == "1 repeated formula text"
    assert finding.body[0].html.startswith("1 formula text appears")
    assert finding.body[1].items == [
        "'Ratio calculation': cm_0, cm_1", "'Ratio calculation': cm_2, cm_3"
    ]


@pytest.mark.parametrize("summaries", [["-", "-"], [" ", "\t"], ["MetricA", "metrica"]])
def test_formula_sentinels_and_case_are_not_equal_formula_evidence(summaries):
    implementation = adapt(cja_snapshot(calculated_metrics=[
        {"id": f"cm_{i}", "formula_summary": text} for i, text in enumerate(summaries)
    ]))
    assert check_calc_identical_formula_text(implementation, ctx("CALC-015")) == []


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
@pytest.mark.parametrize("inventory", [None, [], [{"id": "s_shared"}]])
def test_partial_inventory_reports_evidence_consistently_through_cli(tmp_path, pack, inventory):
    snapshot = cja_snapshot(
        calculated_metrics=[{"id": "cm_a", "segment_references": ["s_shared"]}],
        derived_fields=[{"id": "variables/df", "component_references": ["metrics/unknown"]}],
    )
    if inventory is not None:
        snapshot["segments"] = inventory
    source, html_path, json_path = (tmp_path / name for name in ("input.json", "grade.html", "grade.json"))
    source.write_text(json.dumps(snapshot))
    arguments = [str(source), "--pack", pack, "--output", str(html_path),
                 "--json", str(json_path), "--quiet", "--fail-below", "A"]
    report = grade(adapt(snapshot, source=str(source)), load_rubric(BUNDLED_PACKS_DIR / pack))
    expected_exit = 0 if report.overall_pct >= 90 else 2
    assert main(arguments) == expected_exit
    payload = json.loads(json_path.read_text())
    expected_components = 2 + len(inventory or [])  # one derived field + one calc
    assert payload["components_evaluated"] == expected_components
    assert f"evaluated {expected_components} components" in payload["tldr_html"]
    assert payload == report_to_dict(report)
    html = html_path.read_text()
    assert f"evaluated {expected_components} components" in html
    assert html == render(report)
    findings = {f["id"]: f for f in payload["findings"]}
    assert ("SCH-002" in findings) == (not inventory)
    assert ("CALC-002" in findings) == (not inventory)
    assert "SCH-009" in findings
    for rule_id in {"SCH-002", "CALC-002", "SCH-009"} & findings.keys():
        finding = findings[rule_id]
        assert "unresolved" in finding["title"]
        assert escape(finding["title"]) in html
        assert "does not prove the live implementation is broken" in finding["body"][0]["html"]
        assert "Verify each unresolved ID in the source platform" in finding["body"][-1]["body_html"]
    assert main(arguments) == expected_exit
    assert json_path.read_text() == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert html_path.read_text() == html


@pytest.mark.parametrize("platform", ["cja", "aa"])
def test_segments_and_calculated_metrics_are_counted_without_base_components(platform):
    snapshot = cja_snapshot(segments=[{"id": "s_a"}], calculated_metrics=[{"id": "cm_a"}])
    if platform == "aa":
        snapshot["report_suite"] = {"rsid": "synthetic"}
    implementation = (adapt if platform == "cja" else adapt_aa)(snapshot)
    report = grade(implementation, load_rubric(BUNDLED_PACKS_DIR / "strict"))
    assert report_to_dict(report)["components_evaluated"] == 2
    assert "evaluated 2 components" in render(report)


@pytest.mark.parametrize("platform", ["cja", "aa"])
@pytest.mark.parametrize("prefix", ["s_", "segments/"])
@pytest.mark.parametrize("shape", ["cycle", "self", "chain", "external"])
def test_segment_cycles_use_exported_identity_without_namespace_assumptions(platform, prefix, shape):
    from sdr_grader.rules.checks.segments import check_circular_segments

    first, second = f"{prefix}a", f"{prefix}b"
    refs = {
        "cycle": [[second], [first]],
        "self": [[first], []],
        "chain": [[second], []],
        "external": [[f"{prefix}outside"], []],
    }[shape]
    records = []
    for segment_id, references in zip([first, second], refs, strict=True):
        if platform == "cja":
            records.append({"id": segment_id, "other_segment_references": references})
        else:
            records.append({"id": segment_id, "definition": {
                "func": "segment", "version": [1, 0, 0],
                "container": {"func": "container", "context": "hits", "pred": {
                    "func": "and", "preds": [
                        {"func": "segment-ref", "id": ref} for ref in references
                    ],
                }},
            }})
    snapshot = cja_snapshot(segments=records)
    if platform == "aa":
        snapshot["report_suite"] = {"rsid": "synthetic"}
    implementation = (adapt if platform == "cja" else adapt_aa)(snapshot)
    assert [segment.references for segment in implementation.segments] == refs
    findings = check_circular_segments(implementation, ctx("SEG-004"))
    assert bool(findings) is (shape in {"cycle", "self"})
    if findings:
        assert findings[0].body[1].items == [
            ", ".join(sorted([first, second])) if shape == "cycle" else first
        ]

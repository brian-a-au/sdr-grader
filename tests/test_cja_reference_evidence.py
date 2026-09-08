"""Exporter representation regressions; all identities and evidence are synthetic."""

import json
from copy import deepcopy

import pytest

from sdr_grader.adapters.cja import adapt
from sdr_grader.cli.main import BUNDLED_PACKS_DIR, main
from sdr_grader.core.grader import grade
from sdr_grader.rules.rubric import load_rubric


def snapshot(reference="metrics/visits", summary=None):
    return {
        "metadata": {"Data View ID": "dv1", "Tool Version": "3.11.7"},
        "metrics": [],
        "dimensions": [],
        "calculated_metrics": {
            "metrics": [
                {
                    "id": "cm1",
                    "name": "Session count",
                    "description": "Counts sessions",
                    "metric_references": [reference.rsplit("/", 1)[-1]]
                    if summary is None
                    else summary,
                    "definition_json": json.dumps(
                        {"func": "calc-metric", "formula": {"func": "metric", "name": reference}}
                    ),
                }
            ]
        },
    }


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
@pytest.mark.parametrize("reference", ["metrics/visits", "metrics/deleted"])
def test_full_records_and_canonical_cli_equivalence(tmp_path, pack, reference):
    reports, htmls, exits = [], [], []
    for summary in ([reference], [reference.split("/")[-1]], reference.split("/")[-1]):
        data = snapshot(reference, summary)
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps(data))
        out, machine = tmp_path / "report.html", tmp_path / "report.json"
        for _ in range(2):
            exits.append(
                main(
                    [
                        str(path),
                        "--rubric",
                        str(BUNDLED_PACKS_DIR / pack),
                        "--fail-below",
                        "C",
                        "--output",
                        str(out),
                        "--json",
                        str(machine),
                        "--quiet",
                    ]
                )
            )
            reports.append(json.loads(machine.read_text()))
            htmls.append(out.read_bytes())
    assert all(report == reports[0] for report in reports)
    assert len(set(htmls)) == len(set(exits)) == 1
    ids = {finding["id"] for finding in reports[0]["findings"]}
    assert ("SCH-002" in ids) == (reference == "metrics/deleted")
    assert ("CALC-002" in ids) == (reference == "metrics/deleted")
    if pack == "strict":
        assert (reports[0]["overall_pct"], reports[0]["grade"], exits[0]) == (
            (78, "C+", 0) if reference == "metrics/visits" else (71, "C−", 2)
        )


@pytest.mark.parametrize("records", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_segment_summary_alias_retains_cycles(records, reverse):
    data = snapshot()
    key = "segment_references" if records else "other_segment_references"
    data["segments"] = [
        {"id": "s_a", key: "s_b" if records else ["s_b"]},
        {"id": "s_b", key: "s_a" if records else ["s_a"]},
    ]
    if reverse:
        data["segments"].reverse()
    report = grade(adapt(data), load_rubric(BUNDLED_PACKS_DIR / "strict"))
    assert "SEG-004" in {finding.id for finding in report.findings}


def test_nested_typed_references_preserve_namespaces_and_ignore_literals():
    data = snapshot()
    data["segments"] = [
        {
            "id": "s_a",
            "dimension_references": ["x"],
            "metric_references": ["x"],
            "definition_json": {
                "func": "and",
                "preds": [
                    {
                        "func": "streq",
                        "val": {"func": "attr", "name": "variables/x"},
                        "str": "metrics/literal",
                    },
                    {"func": "gt", "val": {"func": "event", "name": "metrics/x"}, "num": 0},
                ],
            },
        }
    ]
    assert adapt(data).segments[0].references == ["metrics/x", "variables/x"]
    # Only the dimension exists: its suffix must not satisfy the metric.
    data["dimensions"] = [{"id": "variables/x"}]
    report = grade(adapt(data), load_rubric(BUNDLED_PACKS_DIR / "strict"))
    assert "SCH-002" in {finding.id for finding in report.findings}


def test_canonical_definition_adds_missing_evidence_without_hiding_summary_conflicts():
    data = snapshot("metrics/group/x", ["x", "metrics/extra"])
    formula = data["calculated_metrics"]["metrics"][0]
    formula["definition_json"] = {
        "func": "divide",
        "col1": {"func": "metric", "name": "metrics/group/x"},
        "col2": {"func": "metric", "name": "metrics/other/x"},
        "filter": {"func": "segment-ref", "id": "s_missing"},
    }
    assert adapt(data).calculated_metrics[0].references == [
        "metrics/extra",
        "metrics/group/x",
        "metrics/other/x",
        "s_missing",
        "x",
    ]
    # No definition means there is no evidence for expanding a short ID.
    formula["definition_json"] = None
    assert adapt(data).calculated_metrics[0].references == ["metrics/extra", "x"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        0,
        "",
        "-",
        {},
        [None, False, 0, {}],
        "[null, false, 0, {}]",
        "[broken",
        "{broken",
        '"x"',
    ],
)
def test_malformed_summaries_do_not_create_reference_ids(value):
    data = snapshot(summary=value)
    record = data["calculated_metrics"]["metrics"][0]
    record["metric_references"] = value
    record["definition_json"] = None
    assert adapt(data).calculated_metrics[0].references == []


@pytest.mark.parametrize(
    "definition", [None, False, 0, "", "broken", [], '[{"func":"metric","name":"metrics/phantom"}]']
)
def test_unusable_definitions_keep_independent_summary_evidence(definition):
    data = snapshot(summary="metrics/missing, metrics/second")
    data["calculated_metrics"]["metrics"][0]["definition_json"] = definition
    assert adapt(data).calculated_metrics[0].references == ["metrics/missing", "metrics/second"]


def test_reference_order_dedup_and_repeated_execution():
    data = snapshot(summary=["metrics/second", "visits", "metrics/second"])
    first = adapt(data).calculated_metrics[0].references
    other = deepcopy(data)
    other["calculated_metrics"]["metrics"][0]["metric_references"].reverse()
    assert (
        first
        == adapt(other).calculated_metrics[0].references
        == ["metrics/second", "metrics/visits"]
    )


@pytest.mark.parametrize(
    "value", ["[" + "1" * 5000 + "]", "[" * 1100 + "]" * 1100, "[" * 102 + "]" * 102, '["\\udfff"]']
)
def test_embedded_summary_limits_fail_cli_without_reports(tmp_path, capsys, value):
    data = snapshot(summary=value)
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(data))
    out, machine = tmp_path / "report.html", tmp_path / "report.json"
    assert main([str(path), "--output", str(out), "--json", str(machine)]) == 1
    assert not out.exists() and not machine.exists()
    error = capsys.readouterr().err
    assert "reference list" in error and "Traceback" not in error


@pytest.mark.parametrize(
    "field,kind,canonical",
    [
        ("dim", "dimension_references", "variables/group.x"),
        ("dimension", "dimension_references", "variables/group/x"),
        ("metric", "metric_references", "metrics/x"),
        ("seg", "segment_references", "s_x"),
        ("segment", "other_segment_references", "s_x"),
    ],
)
def test_exporter_segment_id_slots(field, kind, canonical):
    data = snapshot()
    short = canonical.rsplit("/", 1)[-1]
    data["segments"] = [
        {
            "id": "s_a",
            kind: [short],
            "definition_json": {"func": "container", "pred": {"func": "exists", field: canonical}},
        }
    ]
    assert adapt(data).segments[0].references == [canonical]


def test_dot_shortening_and_unknown_nodes_do_not_erase_evidence():
    data = snapshot("xdm.group.x", ["x", "metrics/unknown"])
    assert adapt(data).calculated_metrics[0].references == ["metrics/unknown", "xdm.group.x"]
    data["calculated_metrics"]["metrics"][0]["definition_json"] = {
        "func": {"unknown": []},
        "custom": {"func": "future", "id": "metrics/not-a-ref"},
    }
    assert adapt(data).calculated_metrics[0].references == ["metrics/unknown", "x"]


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
@pytest.mark.parametrize("present", [True, False])
@pytest.mark.parametrize("wrapped", [
    {"id": "segments/s_saved"},
    {"segment_id": "segments/s_saved", "name": "Label, not an ID"},
    [None, "", {"id": "segments/s_saved"}],
])
def test_calculated_metric_wrapped_segment_id_resolves_exact_target(pack, present, wrapped):
    # Source: cja_auto_sdr 3.12.0, dcafcf10435a9218ec9632f82dca246581224269,
    # inventory/calculated_metrics.py::_normalize_reference_value and _parse_formula.
    # The exporter retains the wrapper in definition_json but shortens its summary.
    # Synthetic identities characterize that exporter contract, not a customer capture.
    data = snapshot()
    record = data["calculated_metrics"]["metrics"][0]
    record["segment_references"] = ["s_saved"]
    record["definition_json"] = {
        "func": "calc-metric",
        "formula": {
            "func": "segment", "segment_id": wrapped,
            "metric": {"func": "metric", "name": "metrics/visits"},
        },
    }
    data["segments"] = [{"segment_id": "segments/s_saved"}] if present else []
    normalized = adapt(data)
    assert normalized.calculated_metrics[0].references == ["metrics/visits", "segments/s_saved"]
    report = grade(normalized, load_rubric(BUNDLED_PACKS_DIR / pack))
    findings = [f for f in report.findings if f.id in {"SCH-002", "CALC-002"}]
    assert {f.id for f in findings} == (set() if present else {"SCH-002", "CALC-002"})
    for finding in findings:
        assert [item for block in finding.body for item in (block.items or [])] == [
            "calc_metric cm1 -> missing segments/s_saved" if finding.id == "SCH-002"
            else "cm1 -> segments/s_saved"
        ]


def test_unknown_segment_wrapper_cannot_resolve_summary_by_inventory_suffix():
    data = snapshot()
    record = data["calculated_metrics"]["metrics"][0]
    record["segment_references"] = ["s_saved"]
    record["definition_json"] = {
        "func": "segment", "segment_id": {"unrelated": "segments/s_saved"},
    }
    data["segments"] = [{"segment_id": "segments/s_saved"}]
    assert adapt(data).calculated_metrics[0].references == ["s_saved", "visits"]


@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_wrapped_segment_reference_matches_canonical_cli_and_python_reports(tmp_path, pack):
    from sdr_grader.render.json_output import report_to_dict

    reports, htmls, exits = [], [], []
    for value in ("segments/s_saved", {"id": "segments/s_saved"}):
        data = snapshot()
        record = data["calculated_metrics"]["metrics"][0]
        record["segment_references"] = ["s_saved"]
        record["definition_json"] = json.dumps({
            "func": "segment", "segment_id": value,
            "metric": {"func": "metric", "name": "metrics/visits"},
        })
        # Resolving the target must not conceal its missing outgoing dependency.
        data["segments"] = [{
            "segment_id": "segments/s_saved", "metric_references": ["metrics/missing"],
        }]
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps(data))
        out, machine = tmp_path / "report.html", tmp_path / "report.json"
        for _ in range(2):
            exits.append(main([
                str(path), "--rubric", str(BUNDLED_PACKS_DIR / pack),
                "--output", str(out), "--json", str(machine), "--quiet",
            ]))
            reports.append(json.loads(machine.read_text()))
            htmls.append(out.read_bytes())
        direct = grade(adapt(data, source=str(path)), load_rubric(BUNDLED_PACKS_DIR / pack))
        assert reports[-1] == report_to_dict(direct)
        references = [f for f in direct.findings if f.id in {"SCH-002", "CALC-002"}]
        assert [f.id for f in references] == ["SCH-002"]
        assert [item for block in references[0].body for item in (block.items or [])] == [
            "segment segments/s_saved -> missing metrics/missing"
        ]
    assert all(report == reports[0] for report in reports)
    assert len(set(htmls)) == len(set(exits)) == 1


@pytest.mark.parametrize("literal_key", ["str", "list", "glob"])
@pytest.mark.parametrize("as_list", [False, True])
def test_ast_shaped_comparison_literals_are_not_reference_evidence(literal_key, as_list):
    data = snapshot()
    literal = {"func": "metric", "name": "metrics/literal"}
    record = data["calculated_metrics"]["metrics"][0]
    record["definition_json"] = {
        "func": "calc-metric",
        "formula": {
            "func": "metric",
            "name": "metrics/visits",
            literal_key: [literal] if as_list else literal,
        },
    }
    assert adapt(data).calculated_metrics[0].references == ["metrics/visits"]


def test_multi_item_csv_json_and_native_lists_produce_identical_reports():
    from sdr_grader.render import render
    from sdr_grader.render.json_output import report_to_dict

    rubric = load_rubric(BUNDLED_PACKS_DIR / "strict")
    reports, htmls = [], []
    for summary in (
        ["metrics/deleted", "visits"],
        '["visits", "metrics/deleted"]',
        "visits, metrics/deleted, visits",
        " metrics/deleted , visits ",
    ):
        impl = adapt(snapshot(summary=summary))
        assert impl.calculated_metrics[0].references == ["metrics/deleted", "metrics/visits"]
        report = grade(impl, rubric)
        assert (report.overall_pct, report.grade) == (71, "C−")
        reports.append(report_to_dict(report))
        htmls.append(render(report))
    assert all(report == reports[0] for report in reports)
    assert len(set(htmls)) == 1

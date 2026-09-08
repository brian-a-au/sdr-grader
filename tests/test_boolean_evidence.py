"""Selected boolean evidence must never use Python truthiness."""

import json
from pathlib import Path

import pytest

from _rule_test_helpers import component, ctx, impl
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError, RubricValidationError
from sdr_grader.rules.checks.attribution import check_attribution_setting_undocumented
from sdr_grader.rules.checks.governance import check_sdr_doc_absent, check_snapshot_history_absent
from sdr_grader.rules.checks.schema_hygiene import check_persistence_lookback_cap


@pytest.mark.parametrize(
    "check,key,alias",
    [
        (check_snapshot_history_absent, "history_present", "History Present"),
        (check_sdr_doc_absent, "sdr_doc_present", "SDR Doc Present"),
    ],
)
@pytest.mark.parametrize(
    "value,expected", [(True, 0), (False, 1), (" TRUE ", 0), (" fAlSe ", 1), (None, 1)]
)
def test_governance_semantic_values(check, key, alias, value, expected):
    for source in ("metadata", "params"):
        model = impl(raw={"metadata": {key: value}} if source == "metadata" else {})
        context = ctx("GOV", **({key: value} if source == "params" else {}))
        assert len(check(model, context)) == expected


@pytest.mark.parametrize("value", [0, 1, "", "yes", [], {}, {"secret": "do-not-print"}])
@pytest.mark.parametrize(
    "source,error", [("metadata", InvalidSnapshotError), ("params", RubricValidationError)]
)
def test_invalid_selected_governance(value, source, error):
    model = impl(raw={"metadata": {"history_present": value}} if source == "metadata" else {})
    context = ctx("GOV", **({"history_present": value} if source == "params" else {}))
    with pytest.raises(error, match="history_present") as exc:
        check_snapshot_history_absent(model, context)
    assert "do-not-print" not in str(exc.value)


def test_precedence_null_false_and_aliases():
    model = impl(raw={"metadata": {"history_present": {}, "History Present": True}})
    model.history_present = True
    assert check_snapshot_history_absent(model, ctx("GOV")) == []
    assert len(check_snapshot_history_absent(model, ctx("GOV", history_present="false"))) == 1
    assert check_snapshot_history_absent(model, ctx("GOV", history_present=None)) == []
    model.history_present = None
    model.raw["metadata"] = {"history_present": None, "History Present": "true"}
    assert check_snapshot_history_absent(model, ctx("GOV")) == []
    model.raw["metadata"] = {"history_present": False, "History Present": "false"}
    assert len(check_snapshot_history_absent(model, ctx("GOV"))) == 1
    model.raw["metadata"]["History Present"] = True
    with pytest.raises(InvalidSnapshotError, match="metadata"):
        check_snapshot_history_absent(model, ctx("GOV"))
    with pytest.raises(RubricValidationError, match="params"):
        check_snapshot_history_absent(
            model, ctx("GOV", **{"history_present": False, "History Present": True})
        )


@pytest.mark.parametrize(
    "setting_name,nested,check,bucket",
    [
        (
            "attributionSetting",
            {"attributionModel": {"func": "linear"}},
            check_attribution_setting_undocumented,
            "metrics",
        ),
        (
            "persistenceSetting",
            {"allocationModel": {"expiration": {"numPeriods": 120, "granularity": "day"}}},
            check_persistence_lookback_cap,
            "dimensions",
        ),
    ],
)
@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize(
    "value,expected",
    [
        (True, 1),
        (" TrUe ", 1),
        (False, 0),
        (" false ", 0),
        (None, 0),
        (0, None),
        (1, None),
        ("", None),
        ([], None),
        ({}, None),
    ],
)
def test_setting_enabled(setting_name, nested, check, bucket, encoded, value, expected):
    setting = {"enabled": value, **nested}
    c = component(1)
    c.platform_specific[setting_name] = json.dumps(setting) if encoded else setting
    model = impl(**{bucket: [c]})
    if expected is None:
        with pytest.raises(InvalidSnapshotError, match=setting_name + r"\.enabled"):
            check(model, ctx("TEST"))
    else:
        assert len(check(model, ctx("TEST"))) == expected


@pytest.mark.parametrize(
    "setting_name,nested,check,bucket",
    [
        (
            "attributionSetting",
            "attributionModel",
            check_attribution_setting_undocumented,
            "metrics",
        ),
        ("persistenceSetting", "allocationModel", check_persistence_lookback_cap, "dimensions"),
    ],
)
@pytest.mark.parametrize("value", [True, 1, "bad", [], False])
def test_malformed_nested_model(setting_name, nested, check, bucket, value):
    c = component(1)
    c.platform_specific[setting_name] = {"enabled": True, nested: value}
    with pytest.raises(InvalidSnapshotError, match=nested):
        check(impl(**{bucket: [c]}), ctx("TEST"))


def test_cli_invalid_metadata_keeps_existing_reports(tmp_path, capsys):
    data = json.loads((Path(__file__).parent / "fixtures/cja_snapshot_clean.json").read_text())
    data["metadata"]["history_present"] = {"secret": "do-not-print"}
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(data))
    html, output = tmp_path / "out.html", tmp_path / "out.json"
    html.write_text("old html")
    output.write_text("old json")
    assert main([str(source), "--output", str(html), "--json", str(output)]) == 1
    assert html.read_text() == "old html"
    assert output.read_text() == "old json"
    assert "do-not-print" not in capsys.readouterr().err


@pytest.mark.parametrize("platform", ["cja", "aa"])
@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_cli_false_equivalence_and_gate(platform, pack, tmp_path):
    fixture = Path(__file__).parent / f"fixtures/{platform}_snapshot_clean.json"
    data = json.loads(fixture.read_text())
    results = []
    for index, value in enumerate([False, " FALSE "]):
        data["metadata"].update(history_present=value, sdr_doc_present=value)
        source = tmp_path / "snapshot.json"
        source.write_text(json.dumps(data))
        output = tmp_path / f"{index}.json"
        rc = main(
            [
                str(source),
                "--output",
                str(tmp_path / f"{index}.html"),
                "--json",
                str(output),
                "--fail-below",
                "A",
                "--pack",
                pack,
            ]
        )
        results.append((rc, json.loads(output.read_text())))
    assert results[0] == results[1]
    assert results[0][0] == 2


def test_cli_override_validation_and_selected_source(tmp_path, capsys):
    import shutil

    import yaml

    from sdr_grader.rules import packs

    pack = tmp_path / "pack"
    shutil.copytree(Path(packs.__file__).parent / "strict", pack)
    rules_path = pack / "governance.yaml"
    rules = yaml.safe_load(rules_path.read_text())
    rule = next(rule for rule in rules["rules"] if rule["id"] == "GOV-001")
    source = tmp_path / "snapshot.json"
    data = json.loads((Path(__file__).parent / "fixtures/cja_snapshot_clean.json").read_text())
    data["metadata"]["history_present"] = {"secret": "do-not-print"}
    source.write_text(json.dumps(data))
    output = tmp_path / "output.html"
    for value, expected in [(True, 0), (False, 0), ({"secret": "do-not-print"}, 3)]:
        rule["params"]["history_present"] = value
        rules_path.write_text(yaml.safe_dump(rules))
        output.write_text("previous")
        assert main([str(source), "--rubric", str(pack), "--output", str(output)]) == expected
        if expected == 3:
            assert output.read_text() == "previous"
    assert "do-not-print" not in capsys.readouterr().err


@pytest.mark.parametrize("value", [0, 1, "", [], {}])
def test_direct_invalid_runtime_history(value):
    model = impl()
    model.history_present = value
    with pytest.raises(InvalidSnapshotError, match="history_present"):
        check_snapshot_history_absent(model, ctx("GOV"))
    assert check_snapshot_history_absent(model, ctx("GOV", history_present=True)) == []


@pytest.mark.parametrize(
    "setting_name,nested,check,bucket",
    [
        (
            "attributionSetting",
            "attributionModel",
            check_attribution_setting_undocumented,
            "metrics",
        ),
        ("persistenceSetting", "allocationModel", check_persistence_lookback_cap, "dimensions"),
    ],
)
@pytest.mark.parametrize("enabled", [None, False, "false"])
def test_unavailable_disabled_settings_skip_nested_model(
    setting_name, nested, check, bucket, enabled
):
    c = component(1)
    setting = {nested: []}
    if enabled is not None:
        setting["enabled"] = enabled
    c.platform_specific[setting_name] = setting
    assert check(impl(**{bucket: [c]}), ctx("TEST")) == []


def test_persistence_unrecognized_expiration_shape_remains_noop():
    c = component(1)
    c.platform_specific["persistenceSetting"] = {
        "enabled": True,
        "allocationModel": {"expiration": []},
    }
    assert check_persistence_lookback_cap(impl(dimensions=[c]), ctx("TEST")) == []


@pytest.mark.parametrize("include_model", [True, False])
def test_enabled_setting_with_unavailable_model_has_no_fabricated_override(include_model):
    c = component(1)
    setting = {"enabled": True}
    if include_model:
        setting["attributionModel"] = None
    c.platform_specific["attributionSetting"] = setting
    assert check_attribution_setting_undocumented(impl(metrics=[c]), ctx("TEST")) == []

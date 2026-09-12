"""Offline adapter-to-CLI acceptance, score accounting, and trend compatibility."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt as adapt_cja
from sdr_grader.cli.main import BUNDLED_PACKS_DIR, main
from sdr_grader.core.grader import grade
from sdr_grader.render import render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.engine import resolve_effective_rules, run_rules
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend.renderer import _findings_churn
from sdr_grader.trend.runner import build_trend_report

FIXTURES = Path(__file__).parent / "fixtures/reference_grading_policy"
EXPECTED = json.loads((FIXTURES / "acceptance.json").read_text())
FLAG = "exclude_unresolved_calculated_metric_segments"


@pytest.mark.parametrize("case_name", EXPECTED)
def test_exact_policy_fixture_cli_python_and_weights(tmp_path, case_name):
    platform, case, pack = case_name.split("-")
    expected = EXPECTED[case_name]
    source = FIXTURES / f"{platform}_{case}.json"
    snapshot = json.loads(source.read_text())
    impl = (adapt_aa if platform == "aa" else adapt_cja)(snapshot, source=str(source))
    before = asdict(impl)
    rubric = load_rubric(BUNDLED_PACKS_DIR / pack)
    report = grade(impl, rubric)
    assert asdict(impl) == before
    assert (report.overall_pct, report.grade) == (expected["score"], expected["grade"])
    findings = {f.id: f for f in report.findings}
    assert sorted(findings.keys() & {"SCH-002", "CALC-002"}) == expected["reference_findings"]
    rules = resolve_effective_rules(impl, rubric)
    assert len(rules) == expected["effective_rules"]
    for category, weights in expected["weights"].items():
        category_rules = [r for r in rules if r.category == category]
        assert (
            sum(rubric.severity_weights[r.severity] for r in category_rules)
            == weights["denominator"]
        )
        assert (
            sum(rubric.severity_weights[r.severity] for r in category_rules if r.id in findings)
            == weights["failed"]
        )
    if case == "mixed":
        for rule_id in ["SCH-002", "CALC-002"]:
            items = [i for b in findings[rule_id].body for i in (b.items or [])]
            assert len(items) == 1 and "metrics/missing" in items[0]
            assert "segments/missing" not in items[0]
    diagnostics = [p for p in report.methodology.paragraphs if "Unverified reference:" in p]
    assert len(diagnostics) == (1 if case in {"excluded_only", "mixed"} else 0)
    old_rubric = replace(
        rubric,
        rules=[
            replace(r, params={**r.params, FLAG: False}) if r.id in {"SCH-002", "CALC-002"} else r
            for r in rubric.rules
        ],
    )
    assert [f for f in run_rules(impl, old_rubric) if f.id not in {"SCH-002", "CALC-002"}] == [
        f for f in run_rules(impl, rubric) if f.id not in {"SCH-002", "CALC-002"}
    ]
    html_path, json_path = tmp_path / "report.html", tmp_path / "report.json"
    arguments = [
        str(source),
        "--pack",
        pack,
        "--output",
        str(html_path),
        "--json",
        str(json_path),
        "--quiet",
        "--fail-below",
        "A",
    ]
    for _ in range(2):
        assert main(arguments) == expected["fail_below_A_exit"]
        assert json.loads(json_path.read_text()) == report_to_dict(report)
        assert html_path.read_text() == render(report)


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_many_typed_exclusions_through_legacy_snapshot_cli(tmp_path, platform, pack):
    snapshot = json.loads((FIXTURES / f"{platform}_excluded_only.json").read_text())
    record = (
        snapshot["calculated_metrics"][0]
        if platform == "aa"
        else snapshot["calculated_metrics"]["metrics"][0]
    )
    definition = record["definition" if platform == "aa" else "definition_json"]
    definition["formula"]["args"] = [
        {"func": "segment-ref", "id": f'<img onerror="{i:03}">'} for i in range(61)
    ] * 2
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps(snapshot))
    html, machine = tmp_path / "report.html", tmp_path / "report.json"
    args = [str(source), "--pack", pack, "--output", str(html), "--json", str(machine), "--quiet"]
    assert main(args) == 0
    before = html.read_bytes(), machine.read_bytes()
    assert main(args) == 0
    assert (html.read_bytes(), machine.read_bytes()) == before
    assert html.read_text().count("Unverified reference:") == 61
    assert '<img onerror="' not in html.read_text()
    report = json.loads(machine.read_text())
    assert report["schema_version"] == 1
    assert (
        len([p for p in report["methodology"]["paragraphs"] if "Unverified reference:" in p]) == 61
    )


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_excluded_reference_changes_do_not_enter_trend_churn(tmp_path, platform, pack):
    snapshot = json.loads((FIXTURES / f"{platform}_excluded_only.json").read_text())
    (tmp_path / "snapshot_2026-09-01.json").write_text(json.dumps(snapshot))
    record = (
        snapshot["calculated_metrics"][0]
        if platform == "aa"
        else snapshot["calculated_metrics"]["metrics"][0]
    )
    definition = record["definition" if platform == "aa" else "definition_json"]
    definition["formula"]["args"][0]["id"] = "segments/another-missing"
    (tmp_path / "snapshot_2026-09-02.json").write_text(json.dumps(snapshot))
    trend = build_trend_report(tmp_path, load_rubric(BUNDLED_PACKS_DIR / pack))
    assert _findings_churn(trend) == ([], [])
    assert trend.pack_version == "2.1"
    assert all(
        len([p for p in point.report.methodology.paragraphs if "Unverified reference:" in p]) == 1
        for point in trend.points
    )


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_excluded_only_custom_pack_keeps_numeric_default_and_threshold(tmp_path, platform, pack):
    import yaml

    custom = tmp_path / "pack"
    custom.mkdir()
    (custom / "_meta.yaml").write_bytes((BUNDLED_PACKS_DIR / pack / "_meta.yaml").read_bytes())
    files = {"schema_hygiene.yaml": "SCH-002", "calc_metrics.yaml": "CALC-002"}
    for file, rule_id in files.items():
        data = yaml.safe_load((BUNDLED_PACKS_DIR / pack / file).read_text())
        data["rules"] = [r for r in data["rules"] if r["id"] == rule_id]
        (custom / file).write_text(yaml.safe_dump(data))
    machine = tmp_path / "report.json"
    args = [
        str(FIXTURES / f"{platform}_excluded_only.json"),
        "--rubric",
        str(custom),
        "--output",
        str(tmp_path / "report.html"),
        "--json",
        str(machine),
        "--quiet",
        "--fail-below",
        "A",
    ]
    assert main(args) == 0
    report = json.loads(machine.read_text())
    assert report["overall_pct"] == 100
    assert report["tldr_html"].startswith("No scoring rules were assessed")
    assert len(report["methodology"]["skipped"]) == 2
    for file in files:
        data = yaml.safe_load((custom / file).read_text())
        data["rules"][0]["params"] = {}
        (custom / file).write_text(yaml.safe_dump(data))
    assert main(args) == 2
    assert {f["id"] for f in json.loads(machine.read_text())["findings"]} == {"SCH-002", "CALC-002"}

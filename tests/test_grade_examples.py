"""Semantic contracts for the canonical AA/CJA grade example sources."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt as adapt_cja
from sdr_grader.cli.exit_codes import GRADE_BELOW_THRESHOLD, SUCCESS
from sdr_grader.cli.main import main
from sdr_grader.core.grader import grade
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend import build_trend_report

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
STRICT_PACK = ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"

EXPECTED = {
    ("aa", "clean"): {
        "score": 100,
        "grade": "A",
        "categories": [100, 100, 100, 100, 100, 100],
        "findings": [],
    },
    ("aa", "messy"): {
        "score": 55,
        "grade": "F",
        "categories": [44, 60, 80, 78, 100, 0],
        "findings": [
            "GOV-001",
            "GOV-003",
            "SCH-002",
            "CALC-002",
            "NAME-004",
            "SCH-003",
            "SEG-002",
            "GOV-005",
        ],
    },
    ("cja", "clean"): {
        "score": 100,
        "grade": "A",
        "categories": [100, 100, 100, 100, 100, 100],
        "findings": [],
    },
    ("cja", "messy"): {
        "score": 47,
        "grade": "F",
        "categories": [71, 100, 60, 11, 100, 0],
        "findings": [
            "CALC-014",
            "GOV-001",
            "GOV-003",
            "SCH-002",
            "CALC-002",
            "CALC-015",
            "SCH-003",
            "SEG-002",
            "SEG-007",
            "CALC-003",
            "GOV-005",
        ],
    },
}


def _grade_fixture(platform: str, kind: str):
    path = FIXTURES / f"{platform}_snapshot_{kind}.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    adapter = adapt_aa if platform == "aa" else adapt_cja
    implementation = adapter(snapshot, source=str(path.relative_to(ROOT)))
    return grade(implementation, load_rubric(STRICT_PACK))


def _load_script(name: str):
    spec = spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("platform", "kind"), EXPECTED)
def test_grade_example_semantics_are_locked(platform, kind):
    expected = EXPECTED[(platform, kind)]
    report = _grade_fixture(platform, kind)

    assert (report.overall_pct, report.grade) == (expected["score"], expected["grade"])
    assert [category.pct for category in report.categories] == expected["categories"]
    assert [finding.id for finding in report.findings] == expected["findings"]
    methodology = " ".join(str(paragraph) for paragraph in report.methodology.paragraphs)
    assert "stable rule IDs" in methodology
    assert "rubric documentation" in methodology
    assert "sdr-grader repository" in methodology
    assert "source YAML is linked" not in methodology


@pytest.mark.parametrize(("platform", "kind"), EXPECTED)
def test_grade_example_json_shape_and_exit_behavior_are_locked(platform, kind, tmp_path):
    report = _grade_fixture(platform, kind)
    payload = report_to_dict(report)
    output = tmp_path / f"{platform}-{kind}.html"
    json_output = tmp_path / f"{platform}-{kind}.json"

    assert set(payload) == {
        "adapter",
        "categories",
        "components_evaluated",
        "components_skipped",
        "components_skipped_reason",
        "distribution",
        "findings",
        "generated_at",
        "grade",
        "id",
        "instance_id",
        "instance_name",
        "methodology",
        "overall_pct",
        "remediations",
        "rubric",
        "schema_version",
        "tldr_html",
        "tool_url",
        "tool_version",
    }
    assert all(set(category) == {"grade", "name", "pct"} for category in payload["categories"])
    assert all(
        set(finding) == {"actions", "body", "category", "id", "severity", "title"}
        for finding in payload["findings"]
    )

    exit_code = main(
        [
            str(FIXTURES / f"{platform}_snapshot_{kind}.json"),
            "--output",
            str(output),
            "--json",
            str(json_output),
            "--quiet",
            "--fail-below",
            "A",
        ]
    )
    expected_exit = SUCCESS if kind == "clean" else GRADE_BELOW_THRESHOLD
    assert exit_code == expected_exit
    assert output.is_file()
    assert json_output.is_file()


def test_runtime_trend_semantics_are_locked(tmp_path):
    base = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    dates = ["2025-12-01", "2026-01-15", "2026-03-01", "2026-04-25"]
    for index, date in enumerate(dates):
        snapshot = json.loads(json.dumps(base))
        for metric in snapshot["metrics"][: index * 10]:
            metric["description"] = "Backfilled description."
        snapshot["metadata"]["Generation Timestamp"] = f"{date} 09:14:00"
        (tmp_path / f"snapshot_{date}.json").write_text(json.dumps(snapshot), encoding="utf-8")

    trend = build_trend_report(tmp_path, load_rubric(STRICT_PACK))

    assert [(point.report.overall_pct, point.report.grade) for point in trend.points] == [
        (58, "F"),
        (58, "F"),
        (58, "F"),
        (58, "F"),
    ]
    assert [finding.id for finding in trend.first.report.findings] == [
        "CALC-014",
        "GOV-003",
        "SCH-002",
        "CALC-002",
        "CALC-015",
        "SCH-003",
        "SEG-002",
        "SEG-007",
        "CALC-003",
        "GOV-005",
    ]
    assert [finding.id for finding in trend.latest.report.findings] == [
        finding.id for finding in trend.first.report.findings
    ]


def test_generators_are_deterministic_and_semantically_current(tmp_path):
    generate_demo = _load_script("generate_examples").generate
    generate_all = _load_script("generate_grade_examples").generate_all
    generate_trend = _load_script("generate_trend_example").generate

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_reports = generate_all(first_dir / "grades")
    second_reports = generate_all(second_dir / "grades")
    first_trend = generate_trend(first_dir / "trend.html")
    second_trend = generate_trend(second_dir / "trend.html")
    generate_demo(first_dir / "templated-report.html")
    generate_demo(second_dir / "templated-report.html")

    for relative in [
        "grades/grade-aa-clean.html",
        "grades/grade-aa-messy.html",
        "grades/grade-cja-clean.html",
        "grades/grade-cja-messy.html",
        "trend.html",
        "templated-report.html",
    ]:
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()

    assert {
        key: (report.overall_pct, report.grade, len(report.findings))
        for key, report in first_reports.items()
    } == {
        ("cja", "clean"): (100, "A", 0),
        ("cja", "messy"): (47, "F", 11),
        ("aa", "clean"): (100, "A", 0),
        ("aa", "messy"): (55, "F", 8),
    }
    assert all(report.rubric.pack == "strict" for report in second_reports.values())
    assert all(report.rubric.version == "2.0" for report in second_reports.values())
    assert [(point.report.overall_pct, point.report.grade) for point in first_trend.points] == [
        (58, "F"),
        (59, "F"),
        (59, "F"),
        (59, "F"),
    ]
    assert [finding.id for finding in first_trend.latest.report.findings] == [
        finding.id for finding in first_trend.first.report.findings if finding.id != "SCH-003"
    ]
    assert [(point.report.overall_pct, point.report.grade) for point in second_trend.points] == [
        (58, "F"),
        (59, "F"),
        (59, "F"),
        (59, "F"),
    ]


def test_cja_fixture_builder_matches_committed_fixture_sources():
    builder = _load_script("build_cja_fixtures")

    assert builder.build_clean_snapshot() == json.loads(
        (FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8")
    )
    assert builder.build_messy_snapshot() == json.loads(
        (FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8")
    )

"""One normalized segment identity cannot select contradictory graph evidence."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from sdr_grader.adapters import aa, cja
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.grader import grade
from sdr_grader.input.history import matching_snapshot_sibling_exists
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend import build_trend_report

ROOT = Path(__file__).resolve().parents[1]


def snapshot(platform, rows):
    identity = ({"report_suite": {"rsid": "test"}} if platform == "aa"
                else {"metadata": {"Data View ID": "test"}})
    return {**identity, "metrics": [], "dimensions": [], "segments": rows}


def segment(platform, ident="a", target=None):
    definition = {"func": "segment", "id": target} if target else {}
    return {"id": ident, "name": "Documented segment", "description": "Purpose",
            ("definition" if platform == "aa" else "definition_json"): definition}


def adapt(platform, rows):
    return (aa if platform == "aa" else cja).adapt(snapshot(platform, rows), source="input.json")


def rubric(pack="strict"):
    return load_rubric(ROOT / "src/sdr_grader/rules/packs" / pack)


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("change", ["definition", "name", "owner", "normalized_id"])
def test_adapter_rejects_conflicting_normalized_records(platform, reverse, change):
    first = segment(platform, 7 if change == "normalized_id" else "a")
    second = deepcopy(first)
    if change in {"definition", "normalized_id"}:
        second = segment(platform, "7" if change == "normalized_id" else "a", "b")
    elif change == "owner":
        second["owner_id" if platform == "aa" else "owner"] = "someone"
    else:
        second["name"] = "Other name"
    rows = [first, second][:: -1 if reverse else 1]
    with pytest.raises(InvalidSnapshotError, match="segments\\[1\\].*segments\\[0\\]") as exc:
        adapt(platform, rows)
    assert "input.json" in str(exc.value)


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("pack", ["strict", "pragmatic"])
def test_equal_normalized_duplicates_preserve_records_counts_and_grade(platform, pack):
    first = segment(platform, 7)
    second = segment(platform, "7")
    impl = adapt(platform, [first, second])
    before = deepcopy(impl)
    report = grade(impl, rubric(pack))
    assert impl == before
    assert len(impl.segments) == report.components_evaluated == 2
    assert impl.segments[0] == impl.segments[1]


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("reverse", [False, True])
def test_direct_grade_rejects_conflicting_edges(platform, reverse):
    impl = adapt(platform, [segment(platform)])
    first = impl.segments[0]
    impl.segments = [first, replace(first, references=["b"])][:: -1 if reverse else 1]
    with pytest.raises(InvalidSnapshotError, match="segments\\[1\\].*segments\\[0\\]"):
        grade(impl, rubric())


@pytest.mark.parametrize("platform", ["aa", "cja"])
def test_direct_equal_reference_sets_are_canonical_without_mutation(platform):
    impl = adapt(platform, [segment(platform)])
    first = replace(impl.segments[0], references=["b", "external", "b"])
    second = replace(first, references=["external", "b"])
    impl.segments = [first, second]
    before = deepcopy(impl)
    report = grade(impl, rubric())
    assert impl == before
    assert report.components_evaluated == 2


@pytest.mark.parametrize("platform", ["aa", "cja"])
@pytest.mark.parametrize("cycle", [False, True])
def test_unique_graphs_and_cross_kind_identity_remain_valid(platform, cycle):
    impl = adapt(platform, [segment(platform, "a"), segment(platform, "b")])
    impl.segments[0].references = ["b", "external"]
    impl.segments[1].references = ["a"] if cycle else []
    # A metric and a segment may legitimately share an ID.
    component_snapshot = snapshot(platform, [])
    component_snapshot["metrics"] = [{"id": "a", "name": "Metric", "description": "Purpose"}]
    impl.metrics = (aa if platform == "aa" else cja).adapt(component_snapshot).metrics
    report = grade(impl, rubric())
    assert ("SEG-004" in {f.id for f in report.findings}) == cycle
    assert report.components_evaluated == 3


@pytest.mark.parametrize("platform", ["aa", "cja"])
def test_invalid_history_sibling_is_ignored_but_selected_and_trend_fail(platform, tmp_path, capsys):
    old = tmp_path / "snapshot_2026-01-01.json"
    latest = tmp_path / "snapshot_2026-02-01.json"
    bad = snapshot(platform, [segment(platform), segment(platform, target="b")])
    good = snapshot(platform, [])
    old.write_text(json.dumps(bad))
    latest.write_text(json.dumps(good))
    selected = (aa if platform == "aa" else cja).adapt(good, source=str(latest))
    assert not matching_snapshot_sibling_exists(tmp_path, selected_source=latest, selected=selected)
    html, report_json = tmp_path / "output.html", tmp_path / "output.json"
    assert main([str(tmp_path), "--at", "2026-01-01", "--output", str(html),
                 "--json", str(report_json), "--fail-below", "A"]) == 1
    assert "segments[1]" in capsys.readouterr().err
    assert not html.exists() and not report_json.exists()
    with pytest.raises(InvalidSnapshotError, match="segments\\[1\\]"):
        build_trend_report(tmp_path, rubric())
    assert main([str(tmp_path), "--trend", "--output", str(html)]) == 1
    assert not html.exists()

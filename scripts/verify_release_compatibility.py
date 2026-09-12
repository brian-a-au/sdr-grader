#!/usr/bin/env python3
"""Compare the candidate against immutable v1.2.2 and v1.2.9 behavior contracts."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from itertools import groupby
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE_TAG = "v1.2.2"
BASELINE_COMMIT = "1978eb6d6e8d865e66f2dd464624db9a377417de"
PUBLIC_REMOTE = "https://github.com/brian-a-au/sdr-grader.git"
UV_VERSION = "0.11.16"
README_COMMAND = "sdr-grader cja_snapshot_clean.json --output grade.html --json grade.json --quiet"
NORMALIZED_VERSION_FIELD = "tool_version"
NORMALIZED_COPY_FIELDS = (
    "methodology.paragraphs",
    "distribution.charts[].label",
)
APPROVED_CJA_REFERENCE_IDS = frozenset(
    {"metrics/occurrences", "metrics/visits", "metrics/visitors"}
)
APPROVED_REFERENCE_REMEDIATION = (
    "Verify each unresolved ID in the source platform and export the relevant "
    "inventory for the correct data view or report suite. If the reference is "
    "confirmed invalid, restore the component or update its consumers."
)
BASELINE_REFERENCE_REMEDIATIONS = {
    "SCH-002": (
        "Re-create the missing component, or update the segment / calculated "
        "metric to point at the current canonical equivalent."
    ),
    "CALC-002": (
        "Update the formula to reference the current canonical component or "
        "retire the calculated metric."
    ),
}
# The public messy fixture's summary is now displayed with its original case.
# Bind this copy correction to the exact item, including every component ID.
BASELINE_REPEATED_FORMULA_ITEM = (
    "'revenue / visits': calculatedMetrics/cm_rev_per_visit_final, "
    "calculatedMetrics/cm_rev_per_visit_v2, calculatedMetrics/cm_rev_visit_linear, "
    "calculatedMetrics/cm_revenue_per_visit, calculatedMetrics/cm_revenue_visit_corrected, "
    "calculatedMetrics/cm_revpv_lasttouch, calculatedMetrics/cm_rpv_marketing"
)
APPROVED_REPEATED_FORMULA_ITEM = BASELINE_REPEATED_FORMULA_ITEM.replace(
    "'revenue / visits'", "'Revenue / Visits'", 1
)
APPROVED_COMPONENT_COUNTS = {
    ("AA", "clean.prod", 19): 32,
    ("AA", "messy.prod", 75): 79,
    ("CJA", "dv_clean_prod_web", 40): 53,
    ("CJA", "dv_messy_prod_web", 487): 542,
    # The clean trend point adopts the messy fixture's identity, while
    # retaining the clean fixture's inventories.
    ("CJA", "dv_messy_prod_web", 40): 53,
}
FIXTURE_FAIL_BELOW_A_EXITS = {
    "cja_snapshot_clean.json": 0,
    "cja_snapshot_messy.json": 2,
    "aa_snapshot_clean.json": 0,
    "aa_snapshot_messy.json": 2,
}


class CompatibilityError(Exception):
    """The candidate could not be proven compatible with the baseline."""


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=False,
        )
    except OSError as exc:
        raise CompatibilityError(f"could not execute {command[0]!r}") from exc


def _checked_output(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = _run(command, cwd=cwd, env=env, capture=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CompatibilityError(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout.strip()


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "PYTHONNOUSERSITE": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _verify_uv(uv: str, *, repo_root: Path, environment: dict[str, str]) -> None:
    output = _checked_output([uv, "--version"], cwd=repo_root, env=environment)
    if output.split()[:2] != ["uv", UV_VERSION]:
        raise CompatibilityError(f"uv {UV_VERSION} is required, got {output!r}")


def _fetch_and_verify_baseline(repo_root: Path, environment: dict[str, str], *,
                               tag: str = BASELINE_TAG, commit: str = BASELINE_COMMIT) -> None:
    fetch = [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "core.askPass=",
        "fetch",
        "--no-tags",
        "--force",
        PUBLIC_REMOTE,
        f"+refs/tags/{tag}:refs/tags/{tag}",
    ]
    result = _run(fetch, cwd=repo_root, env=environment, capture=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CompatibilityError(f"credential-free baseline tag fetch failed: {detail}")
    peeled = _checked_output(
        ["git", "rev-parse", f"refs/tags/{tag}^{{}}"],
        cwd=repo_root,
        env=environment,
    )
    if peeled != commit:
        raise CompatibilityError(f"{tag} peeled to {peeled}, expected {commit}")


def _extract_baseline(repo_root: Path, destination: Path, environment: dict[str, str], *,
                      commit: str = BASELINE_COMMIT) -> None:
    archive_path = destination.parent / "baseline.tar"
    result = _run(
        ["git", "archive", "--format=tar", "-o", str(archive_path), commit],
        cwd=repo_root,
        env=environment,
        capture=True,
    )
    if result.returncode != 0:
        raise CompatibilityError("could not archive the verified baseline commit")
    destination.mkdir()
    resolved_destination = destination.resolve()
    try:
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                resolved = (destination / member.name).resolve()
                if not resolved.is_relative_to(resolved_destination):
                    raise CompatibilityError("baseline archive member escapes its root")
            archive.extractall(destination, filter="data")
    except (OSError, tarfile.TarError) as exc:
        raise CompatibilityError("could not extract the verified baseline commit") from exc


def _sync_environment(
    uv: str,
    *,
    source_root: Path,
    environment_root: Path,
    base_environment: dict[str, str],
) -> dict[str, str]:
    environment = base_environment.copy()
    environment.update(
        {
            "VIRTUAL_ENV": str(environment_root),
            "UV_PROJECT_ENVIRONMENT": str(environment_root),
        }
    )
    create = _run(
        [uv, "venv", "--python", "3.12", str(environment_root)],
        cwd=source_root,
        env=environment,
        capture=True,
    )
    if create.returncode != 0:
        raise CompatibilityError(f"could not create environment for {source_root.name}")
    sync = _run(
        [
            uv,
            "sync",
            "--locked",
            "--no-dev",
            "--no-editable",
            "--active",
            "--project",
            str(source_root),
        ],
        cwd=source_root,
        env=environment,
        capture=True,
    )
    if sync.returncode != 0:
        detail = (sync.stderr or sync.stdout or "").strip()
        raise CompatibilityError(f"locked sync failed for {source_root.name}: {detail}")
    return environment


def _readme_arguments(repo_root: Path) -> list[str]:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    matches = re.findall(r"^sdr-grader cja_snapshot_clean\.json .*?$", readme, re.MULTILINE)
    if matches != [README_COMMAND]:
        raise CompatibilityError(
            "README must contain exactly the canonical first-run command argument sequence"
        )
    return shlex.split(matches[0])


def _environment_paths(environment_root: Path) -> tuple[Path, Path]:
    scripts = "Scripts" if os.name == "nt" else "bin"
    executable = "sdr-grader.exe" if os.name == "nt" else "sdr-grader"
    python = "python.exe" if os.name == "nt" else "python"
    return environment_root / scripts / executable, environment_root / scripts / python


def _normalize_report(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized[NORMALIZED_VERSION_FIELD] = "<normalized-version>"
    methodology = normalized.get("methodology")
    if isinstance(methodology, dict) and "paragraphs" in methodology:
        methodology["paragraphs"] = "<normalized-copy>"
    distribution = normalized.get("distribution")
    if isinstance(distribution, dict):
        for chart in distribution.get("charts", []):
            if isinstance(chart, dict) and "label" in chart:
                chart["label"] = "<normalized-copy>"
    return normalized


def _expected_candidate_from_baseline(baseline: dict[str, Any]) -> dict[str, Any]:
    """Apply only reviewed reference-resolution and exact copy deltas."""
    expected = copy.deepcopy(baseline)
    _transform_reports(expected)
    return expected


def _transform_reports(value: Any) -> None:
    if isinstance(value, dict):
        if {"schema_version", "findings", "categories"}.issubset(value):
            _transform_reference_findings(value)
            _transform_component_count(value)
        for child in value.values():
            _transform_reports(child)
    elif isinstance(value, list):
        for child in value:
            _transform_reports(child)


def _transform_component_count(report: dict[str, Any]) -> None:
    """Account for segments/calculated metrics in these exact public cases."""
    platform = report.get("adapter", {}).get("platform")
    old_count = report.get("components_evaluated")
    new_count = APPROVED_COMPONENT_COUNTS.get((platform, report.get("instance_id"), old_count))
    if new_count is None:
        return
    noun = "data view" if platform == "CJA" else "report suite"
    old_copy = f"The grader evaluated {old_count} components in this {noun} "
    new_copy = f"The grader evaluated {new_count} components in this {noun} "
    tldr = report.get("tldr_html")
    if not isinstance(tldr, str) or tldr.count(old_copy) != 1:
        raise CompatibilityError("unexpected public component-count copy in v1.2.2 baseline")
    report["components_evaluated"] = new_count
    report["tldr_html"] = tldr.replace(old_copy, new_copy, 1)


def _transform_reference_findings(report: dict[str, Any]) -> None:
    is_cja = report.get("adapter", {}).get("platform") == "CJA"
    transformed = []
    for finding in report["findings"]:
        rule_id = finding.get("id")
        if is_cja and rule_id == "CALC-015":
            for block in finding.get("body", []):
                if block.get("kind") == "components":
                    block["items"] = [
                        APPROVED_REPEATED_FORMULA_ITEM
                        if item == BASELINE_REPEATED_FORMULA_ITEM
                        else item
                        for item in block.get("items", [])
                    ]
        if rule_id not in {"SCH-002", "CALC-002"}:
            transformed.append(finding)
            continue
        blocks = finding.get("body", [])
        paragraph = next((block for block in blocks if block.get("kind") == "paragraph"), None)
        components = next((block for block in blocks if block.get("kind") == "components"), None)
        if paragraph is None or components is None or not isinstance(components.get("items"), list):
            raise CompatibilityError(f"unexpected {rule_id} finding shape in v1.2.2 baseline")
        if is_cja:
            components["items"] = [
                item
                for item in components["items"]
                if _referenced_id(rule_id, item) not in APPROVED_CJA_REFERENCE_IDS
            ]
            # PR #63 sorts references inside each CJA consumer. Transform only
            # baseline expectations: candidate contents, multiplicity, consumer
            # order, scores and all other findings still compare exactly.
            components["items"] = [
                item
                for _, group in groupby(
                    components["items"], key=lambda item: item.partition(" -> ")[0]
                )
                for item in sorted(group)
            ]
        count = len(components["items"])
        if not count:
            continue
        if rule_id == "SCH-002":
            finding["title"] = f"{count} unresolved reference{'s' if count != 1 else ''}"
            paragraph["html"] = (
                f"{count} reference{'s are' if count != 1 else ' is'} unresolved — "
                "segments or calculated metrics point at IDs not found in this snapshot. "
                "This does not prove the live implementation is broken: the export may "
                "omit components or inventories. Verify the reference in the source "
                "platform and re-export the relevant inventory before changing it."
            )
        else:
            finding["title"] = (
                f"{count} unresolved calculated metric reference{'s' if count != 1 else ''}"
            )
            paragraph["html"] = (
                f"{count} calculated metric reference{'s are' if count != 1 else ' is'} "
                "unresolved — the formula points at components, segments, or other "
                "calculated metrics not found in this snapshot. This does not prove the "
                "live implementation is broken: the export may omit components or "
                "inventories. Verify the reference in the source platform and re-export "
                "the relevant inventory before changing it."
            )
        for block in blocks:
            if (
                block.get("kind") == "section"
                and block.get("label") == "How to remediate"
                and block.get("body_html") == BASELINE_REFERENCE_REMEDIATIONS[rule_id]
            ):
                block["body_html"] = APPROVED_REFERENCE_REMEDIATION
        transformed.append(finding)
    report["findings"] = transformed
    for remediation in report.get("remediations", []):
        for rule_id, old_copy in BASELINE_REFERENCE_REMEDIATIONS.items():
            if remediation.get("refs") == [rule_id] and remediation.get("text") == old_copy:
                remediation["text"] = APPROVED_REFERENCE_REMEDIATION


def _referenced_id(rule_id: str, item: Any) -> str | None:
    if not isinstance(item, str):
        return None
    separator = " -> missing " if rule_id == "SCH-002" else " -> "
    _, found, reference_id = item.partition(separator)
    return reference_id if found else None


def _verify_expected_candidate(candidate: dict[str, Any], baseline: dict[str, Any]) -> None:
    if candidate != _expected_candidate_from_baseline(baseline):
        raise CompatibilityError(
            "candidate structured scores/findings/categories/exit/trend/schema differ "
            "from v1.2.2 beyond the approved CJA reference-resolution, exact copy, "
            "reference ordering, and public component-count corrections "
            "after normalizing only tool_version, " + ", ".join(NORMALIZED_COPY_FIELDS)
        )


def _run_grades(
    *,
    environment_root: Path,
    environment: dict[str, str],
    work_root: Path,
    fixture_root: Path,
    readme_arguments: list[str],
) -> dict[str, Any]:
    console, python = _environment_paths(environment_root)
    work_root.mkdir(parents=True)
    probe = _run(
        [
            str(python),
            "-c",
            (
                "import pathlib,sys,sdr_grader; "
                "checkout=pathlib.Path(sys.argv[1]).resolve(); "
                "origin=pathlib.Path(sdr_grader.__file__).resolve(); "
                "assert not origin.is_relative_to(checkout), origin; "
                "assert all(not pathlib.Path(p or '.').resolve().is_relative_to(checkout) "
                "for p in sys.path), sys.path"
            ),
            str(ROOT),
        ],
        cwd=work_root,
        env=environment,
        capture=True,
    )
    if probe.returncode != 0:
        raise CompatibilityError("installed-package import escaped into the source checkout")

    canonical_fixture = fixture_root / "cja_snapshot_clean.json"
    results: dict[str, Any] = {
        "readme": _run_report_case(
            console=console,
            environment=environment,
            case_root=work_root / "readme-command",
            fixture=canonical_fixture,
            arguments=readme_arguments[1:],
            expected_exit=0,
            case_name="exact README command",
        ),
        "bundled": _run_report_case(
            console=console,
            environment=environment,
            case_root=work_root / "bundled-distribution",
            fixture=canonical_fixture,
            arguments=[
                *readme_arguments[1:],
                "--distribution-data",
                "bundled",
            ],
            expected_exit=0,
            case_name="bundled distribution",
        ),
        "fixtures": {},
    }

    fixture_results: dict[str, Any] = results["fixtures"]
    for filename, expected_threshold_exit in FIXTURE_FAIL_BELOW_A_EXITS.items():
        fixture = fixture_root / filename
        fixture_case = work_root / "fixture-matrix" / fixture.stem
        normal_arguments = [
            filename,
            "--output",
            "grade.html",
            "--json",
            "grade.json",
            "--quiet",
        ]
        normal = _run_report_case(
            console=console,
            environment=environment,
            case_root=fixture_case / "normal",
            fixture=fixture,
            arguments=normal_arguments,
            expected_exit=0,
            case_name=f"normal {filename}",
        )
        threshold = _run_report_case(
            console=console,
            environment=environment,
            case_root=fixture_case / "fail-below-a",
            fixture=fixture,
            arguments=[*normal_arguments, "--fail-below", "A"],
            expected_exit=expected_threshold_exit,
            case_name=f"--fail-below A {filename}",
        )
        fixture_results[filename] = {
            "normal_exit": normal["exit"],
            "report": normal["report"],
            "fail_below_a_exit": threshold["exit"],
            "fail_below_a_report": threshold["report"],
        }

    trend_dir = work_root / "trend-input"
    trend_dir.mkdir()
    _write_nontrivial_trend_inputs(fixture_root, trend_dir)
    trend_probe = (
        "import json,sys; from sdr_grader.rules.rubric import load_rubric; "
        "from sdr_grader.cli.main import BUNDLED_PACKS_DIR; "
        "from sdr_grader.trend.runner import build_trend_report; "
        "from sdr_grader.render.json_output import REPORT_SCHEMA_VERSION,report_to_dict; "
        "trend=build_trend_report(sys.argv[1],load_rubric(BUNDLED_PACKS_DIR/'strict')); "
        "print(json.dumps({'schema_version':REPORT_SCHEMA_VERSION,'instance_id':trend.instance_id,"
        "'platform':trend.platform,'points':[{'timestamp':p.timestamp.isoformat(),"
        "'report':report_to_dict(p.report)} for p in trend.points]},sort_keys=True))"
    )
    trend = _run(
        [str(python), "-c", trend_probe, str(trend_dir)],
        cwd=work_root,
        env=environment,
        capture=True,
    )
    if trend.returncode != 0:
        raise CompatibilityError(f"trend probe failed: {trend.stderr.strip()}")
    trend_payload = json.loads(trend.stdout)
    for point in trend_payload["points"]:
        point["report"] = _normalize_report(point["report"])
    trend_scores = [point["report"]["overall_pct"] for point in trend_payload["points"]]
    if len(trend_scores) != 2 or len(set(trend_scores)) != 2:
        raise CompatibilityError("trend probe did not exercise a nontrivial two-score series")
    results["trend"] = {"exit": trend.returncode, "report": trend_payload}
    return results


def _run_report_case(
    *,
    console: Path,
    environment: dict[str, str],
    case_root: Path,
    fixture: Path,
    arguments: list[str],
    expected_exit: int,
    case_name: str,
) -> dict[str, Any]:
    if not fixture.is_file():
        raise CompatibilityError(f"required compatibility fixture is missing: {fixture.name}")
    case_root.mkdir(parents=True)
    shutil.copyfile(fixture, case_root / fixture.name)
    result = _run(
        [str(console), *arguments],
        cwd=case_root,
        env=environment,
        capture=True,
    )
    if result.returncode != expected_exit:
        raise CompatibilityError(
            f"{case_name} exited {result.returncode}, expected {expected_exit}"
        )
    output = case_root / "grade.json"
    if not output.is_file() or not (case_root / "grade.html").is_file():
        raise CompatibilityError(f"{case_name} did not create HTML and JSON")
    payload = json.loads(output.read_text(encoding="utf-8"))
    required = {"schema_version", "overall_pct", "findings", "categories"}
    if not required.issubset(payload):
        raise CompatibilityError(f"{case_name} JSON is missing structured contract fields")
    return {
        "exit": result.returncode,
        "report": _normalize_report(payload),
    }


def _write_nontrivial_trend_inputs(fixture_root: Path, trend_dir: Path) -> None:
    try:
        clean = json.loads((fixture_root / "cja_snapshot_clean.json").read_text())
        messy = json.loads((fixture_root / "cja_snapshot_messy.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CompatibilityError("could not prepare current CJA trend fixtures") from exc
    clean["data_view"] = copy.deepcopy(messy["data_view"])
    for key in ("Data View ID", "Data View Name"):
        clean["metadata"][key] = messy["metadata"][key]
    (trend_dir / "snapshot_2026-01-01.json").write_text(
        json.dumps(clean, sort_keys=True),
        encoding="utf-8",
    )
    (trend_dir / "snapshot_2026-02-01.json").write_text(
        json.dumps(messy, sort_keys=True),
        encoding="utf-8",
    )


def verify_compatibility(repo_root: Path = ROOT, *, uv: str = "uv") -> None:
    repo_root = Path(repo_root).resolve()
    environment = _clean_environment()
    _verify_uv(uv, repo_root=repo_root, environment=environment)
    _fetch_and_verify_baseline(repo_root, environment)
    readme_arguments = _readme_arguments(repo_root)

    with tempfile.TemporaryDirectory(prefix="sdr-grader-compat-") as temporary:
        temp_root = Path(temporary).resolve()
        if temp_root.is_relative_to(repo_root):
            raise CompatibilityError("compatibility workspace must be outside the checkout")
        baseline_source = temp_root / "baseline-source"
        _extract_baseline(repo_root, baseline_source, environment)
        candidate_env = temp_root / "candidate-env"
        baseline_env = temp_root / "baseline-env"
        candidate_environment = _sync_environment(
            uv,
            source_root=repo_root,
            environment_root=candidate_env,
            base_environment=environment,
        )
        baseline_environment = _sync_environment(
            uv,
            source_root=baseline_source,
            environment_root=baseline_env,
            base_environment=environment,
        )
        fixture_root = repo_root / "tests" / "fixtures"
        candidate = _run_grades(
            environment_root=candidate_env,
            environment=candidate_environment,
            work_root=temp_root / "candidate-output",
            fixture_root=fixture_root,
            readme_arguments=readme_arguments,
        )
        baseline = _run_grades(
            environment_root=baseline_env,
            environment=baseline_environment,
            work_root=temp_root / "baseline-output",
            fixture_root=fixture_root,
            readme_arguments=readme_arguments,
        )
        policy = _load_policy_contract(fixture_root)
        expected_candidate = _apply_policy_deltas(
            _expected_candidate_from_baseline(baseline), policy["public_deltas"]
        )
        if not _exact_json_equal(candidate, expected_candidate):
            raise CompatibilityError("public matrix differs beyond exact reference-policy deltas")


# This gate is deliberately separate from the historical v1.2.2 transforms.
CORRECTNESS_BASELINE_TAG = "v1.2.9"
CORRECTNESS_BASELINE_COMMIT = "9687fcc66622d454cc121cd49daa319c0c01a939"


def _correctness_payload(value: Any) -> Any:
    """Only package identity differs unconditionally; retain every other field."""
    if isinstance(value, dict):
        return {k: "<package-version>" if k == "tool_version" else _correctness_payload(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_correctness_payload(v) for v in value]
    return value


def _exact_json_equal(before: Any, after: Any) -> bool:
    """Compare decoded JSON without equating booleans, integers, and floats."""
    if type(before) is not type(after):
        return False
    if isinstance(before, dict):
        return before.keys() == after.keys() and all(
            _exact_json_equal(value, after[key]) for key, value in before.items()
        )
    if isinstance(before, list):
        return len(before) == len(after) and all(
            _exact_json_equal(a, b) for a, b in zip(before, after, strict=True)
        )
    return before == after


def _exact_deltas(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if _exact_json_equal(before, after):
        return []
    if isinstance(before, dict) and isinstance(after, dict) and before.keys() == after.keys():
        return [delta for key in sorted(before) for delta in _exact_deltas(
            before[key], after[key], path + "/" + key.replace("~", "~0").replace("/", "~1"))]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [delta for i, (a, b) in enumerate(zip(before, after, strict=True))
                for delta in _exact_deltas(a, b, path + f"/{i}")]
    return [{"path": path, "before": before, "after": after}]


def _verify_correctness_case(name, baseline, candidate, contract):
    if not _exact_json_equal(baseline, contract["baseline"]):
        raise CompatibilityError(f"{name}: reviewed v1.2.9 baseline outcome drifted")
    if not _exact_json_equal(candidate, contract["candidate"]):
        raise CompatibilityError(f"{name}: candidate differs beyond exact approved deltas")
    if not _exact_json_equal(_exact_deltas(baseline, candidate), contract["deltas"]):
        raise CompatibilityError(f"{name}: recorded exact deltas do not match outcomes")


_TREND_PROBE = '''import json,sys
from sdr_grader.cli.main import BUNDLED_PACKS_DIR
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.trend.runner import build_trend_report
from sdr_grader.render.json_output import report_to_dict
trend=build_trend_report('snapshots',load_rubric(BUNDLED_PACKS_DIR/sys.argv[1]))
print(json.dumps({'instance_id':trend.instance_id,'platform':trend.platform,'points':[
 {'timestamp':p.timestamp.isoformat(),'source':p.source,'report':report_to_dict(p.report)} for p in trend.points]},sort_keys=True))
'''


def _run_correctness_case(*, console, python, environment, case_root, fixture_root, case):
    """Run twice, preserving complete report or typed contextual error outcomes."""
    case_root.mkdir(parents=True)
    for filename, data in case.get("files", {}).items():
        path = case_root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    if "fixture" in case:
        shutil.copyfile(fixture_root / case["fixture"], case_root / "input.json")
    rubric_args = ["--pack", case.get("pack", "strict")]
    if "rubric" in case:
        # YAML is a superset of JSON; avoid importing candidate dependencies here.
        (case_root / "pack").mkdir()
        for filename, data in case["rubric"].items():
            (case_root / "pack" / filename).write_text(json.dumps(data), encoding="utf-8")
        rubric_args = ["--rubric", "pack"]
    trend = case.get("mode") == "trend"
    args = [str(console), case.get("input", "input.json"), *rubric_args,
            "--output", "grade.html", "--quiet", "--fail-below", "A"]
    args += ["--trend"] if trend else ["--json", "grade.json"]
    if case.get("mode") == "at":
        args += ["--at", "2026-04-25T00:00:00Z"]
    previous = None
    for _ in range(2):
        for filename in ("grade.html", "grade.json"):
            (case_root / filename).unlink(missing_ok=True)
        result = _run(args, cwd=case_root, env=environment, capture=True)
        files = {name: (case_root / name).read_bytes() for name in ("grade.html", "grade.json")
                 if (case_root / name).exists()}
        if result.returncode in (1, 3):
            if files:
                raise CompatibilityError(f"{case['name']}: error published success artifacts")
            prefix = "rubric error:" if result.returncode == 3 else "error:"
            diagnostic = result.stderr.strip()
            if not diagnostic.startswith(prefix) or "Traceback" in diagnostic:
                raise CompatibilityError(f"{case['name']}: untyped failure: {diagnostic}")
            outcome = {"kind": "rubric-error" if result.returncode == 3 else "invalid-input",
                       "exit": result.returncode, "diagnostic": diagnostic,
                       "html_present": False, "json_present": False}
        elif result.returncode in (0, 2):
            if "grade.html" not in files or (not trend and "grade.json" not in files):
                raise CompatibilityError(f"{case['name']}: success missing reports")
            if trend:
                probe = _run([str(python), "-c", _TREND_PROBE, case['pack']],
                             cwd=case_root, env=environment, capture=True)
                if probe.returncode:
                    raise CompatibilityError(f"{case['name']}: trend structure probe failed")
                payload = json.loads(probe.stdout)
            else:
                payload = json.loads(files["grade.json"])
                if not {"schema_version", "overall_pct", "findings", "categories"} <= payload.keys():
                    raise CompatibilityError(f"{case['name']}: missing report contract")
            outcome = {"kind": "report", "exit": result.returncode,
                       "report": _correctness_payload(payload), "html_present": True,
                       "json_present": not trend}
        else:
            raise CompatibilityError(f"{case['name']}: unexpected CLI exit {result.returncode}")
        observed = (outcome, files)
        if previous is not None and observed != previous:
            raise CompatibilityError(f"{case['name']}: repeated outputs are not deterministic")
        previous = observed
    return outcome


def _load_policy_contract(fixtures: Path) -> dict[str, Any]:
    contract = json.loads((fixtures / "reference_grading_policy/compatibility.json").read_text())
    if (contract["package_version"], contract["rubric_version"], contract["schema_version"]) != (
        "1.4.0", "2.1", 1
    ):
        raise CompatibilityError("reference-policy expectation identity differs")
    return contract


def _apply_policy_deltas(original: Any, deltas: list[dict[str, Any]]) -> Any:
    """Apply exact reviewed pointer changes without normalizing candidate behavior."""
    expected = copy.deepcopy(original)
    for delta in deltas:
        path = delta["path"]
        if path == "":
            if not _exact_json_equal(expected, delta["before"]):
                raise CompatibilityError("policy root before value differs")
            expected = copy.deepcopy(delta["after"])
            continue
        if not isinstance(path, str) or not path.startswith("/"):
            raise CompatibilityError("policy delta has an invalid JSON pointer")
        tokens = [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]
        parent = expected
        try:
            for token in tokens[:-1]:
                parent = parent[int(token)] if isinstance(parent, list) else parent[token]
            key = int(tokens[-1]) if isinstance(parent, list) else tokens[-1]
            if not _exact_json_equal(parent[key], delta["before"]):
                raise CompatibilityError(f"policy before value differs at {path}")
            parent[key] = copy.deepcopy(delta["after"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CompatibilityError(f"policy pointer does not identify an existing value: {path}") from exc
    if not _exact_json_equal(_exact_deltas(original, expected), deltas):
        raise CompatibilityError("policy deltas are not the exact canonical change list")
    return expected


def _verify_policy_correctness_case(name, baseline, candidate, legacy_contract, policy_deltas):
    # Verify the immutable historical contract before applying the separate policy layer.
    _verify_correctness_case(name, baseline, legacy_contract["candidate"], legacy_contract)
    expected = _apply_policy_deltas(legacy_contract["candidate"], policy_deltas)
    if not _exact_json_equal(candidate, expected):
        raise CompatibilityError(f"{name}: candidate differs beyond exact reference-policy deltas")


def _run_correctness_matrix(*, environment_root, environment, work_root, fixture_root):
    console, python = _environment_paths(environment_root)
    cases = json.loads((fixture_root / "correctness_1_3/cases.json").read_text())
    return {case["name"]: _run_correctness_case(
        console=console, python=python, environment=environment,
        case_root=work_root / case["name"], fixture_root=fixture_root, case=case)
        for case in cases}


def verify_correctness_compatibility(repo_root: Path = ROOT, *, uv: str = "uv") -> None:
    repo_root = Path(repo_root).resolve()
    environment = _clean_environment()
    _verify_uv(uv, repo_root=repo_root, environment=environment)
    _fetch_and_verify_baseline(repo_root, environment, tag=CORRECTNESS_BASELINE_TAG,
                               commit=CORRECTNESS_BASELINE_COMMIT)
    fixtures = repo_root / "tests/fixtures"
    expected = json.loads((fixtures / "correctness_1_3/expectations.json").read_text())
    policy = _load_policy_contract(fixtures)
    if expected["baseline_commit"] != CORRECTNESS_BASELINE_COMMIT:
        raise CompatibilityError("correctness expectation baseline identity differs")
    with tempfile.TemporaryDirectory(prefix="sdr-grader-correctness-") as temporary:
        temp = Path(temporary).resolve()
        if temp.is_relative_to(repo_root):
            raise CompatibilityError("correctness workspace must be outside the checkout")
        baseline_source = temp / "baseline-source"
        _extract_baseline(repo_root, baseline_source, environment, commit=CORRECTNESS_BASELINE_COMMIT)
        outcomes = []
        for label, source in [("baseline", baseline_source), ("candidate", repo_root)]:
            env_root = temp / f"{label}-env"
            env = _sync_environment(uv, source_root=source, environment_root=env_root,
                                    base_environment=environment)
            _, python = _environment_paths(env_root)
            origin = _checked_output(
                [str(python), "-c", "import sdr_grader; print(sdr_grader.__file__)"],
                cwd=temp, env=env)
            if not Path(origin).resolve().is_relative_to(env_root.resolve()):
                raise CompatibilityError(f"{label}: correctness import escaped installed environment")
            outcomes.append(_run_correctness_matrix(environment_root=env_root, environment=env,
                             work_root=temp / label, fixture_root=fixtures))
        baseline, candidate = outcomes
        if baseline.keys() != expected["cases"].keys() or candidate.keys() != baseline.keys():
            raise CompatibilityError("correctness case matrix differs from reviewed contract")
        if policy["correctness_cases"].keys() != baseline.keys():
            raise CompatibilityError("reference-policy case matrix differs")
        for name in baseline:
            _verify_policy_correctness_case(
                name, baseline[name], candidate[name], expected["cases"][name],
                policy["correctness_cases"][name]
            )
    print(f"v1.2.9 correctness compatibility verified: {len(baseline)} exact outcomes; "
          "all five corrections, both platforms/packs, custom packs, typed errors, "
          "threshold exits and repeated report determinism")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(argv)
    try:
        verify_compatibility(args.repo_root, uv=args.uv)
        verify_correctness_compatibility(args.repo_root, uv=args.uv)
    except (CompatibilityError, OSError, json.JSONDecodeError) as exc:
        print(f"compatibility verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        "v1.2.2 compatibility verified: approved reference, exact copy, "
        "and public component-count corrections match; "
        "scores, categories, exits, trend structure, schema, and other findings are unchanged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

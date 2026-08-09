#!/usr/bin/env python3
"""Compare the candidate package with the immutable v1.2.2 behavior baseline."""

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


def _fetch_and_verify_baseline(repo_root: Path, environment: dict[str, str]) -> None:
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
        f"+refs/tags/{BASELINE_TAG}:refs/tags/{BASELINE_TAG}",
    ]
    result = _run(fetch, cwd=repo_root, env=environment, capture=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CompatibilityError(f"credential-free baseline tag fetch failed: {detail}")
    peeled = _checked_output(
        ["git", "rev-parse", f"refs/tags/{BASELINE_TAG}^{{}}"],
        cwd=repo_root,
        env=environment,
    )
    if peeled != BASELINE_COMMIT:
        raise CompatibilityError(f"{BASELINE_TAG} peeled to {peeled}, expected {BASELINE_COMMIT}")


def _extract_baseline(repo_root: Path, destination: Path, environment: dict[str, str]) -> None:
    archive_path = destination.parent / "baseline.tar"
    result = _run(
        ["git", "archive", "--format=tar", "-o", str(archive_path), BASELINE_COMMIT],
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
        if candidate != baseline:
            raise CompatibilityError(
                "candidate structured scores/findings/categories/exit/trend/schema differ "
                "from v1.2.2 after normalizing only tool_version, "
                + ", ".join(NORMALIZED_COPY_FIELDS)
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(argv)
    try:
        verify_compatibility(args.repo_root, uv=args.uv)
    except (CompatibilityError, OSError, json.JSONDecodeError) as exc:
        print(f"compatibility verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        "v1.2.2 compatibility verified: scores, findings, categories, exits, "
        "trend, and schema are unchanged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

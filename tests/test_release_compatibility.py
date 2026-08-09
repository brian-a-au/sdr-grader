from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_release_compatibility.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_release_compatibility", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compatibility_baseline_and_normalization_are_explicit_and_narrow():
    module = _load_module()
    report = {
        "tool_version": "1.2.2",
        "overall_pct": 87,
        "categories": [{"name": "schema", "pct": 91}],
        "findings": [{"rule_id": "SCH-001"}],
        "methodology": {"paragraphs": ["new copy"], "other": "preserved"},
        "distribution": {"charts": [{"label": "new copy", "svg": "preserved"}]},
    }

    normalized = module._normalize_report(report)

    assert module.BASELINE_TAG == "v1.2.2"
    assert module.BASELINE_COMMIT == "1978eb6d6e8d865e66f2dd464624db9a377417de"
    assert module.UV_VERSION == "0.11.16"
    assert module.NORMALIZED_COPY_FIELDS == (
        "methodology.paragraphs",
        "distribution.charts[].label",
    )
    assert module.FIXTURE_FAIL_BELOW_A_EXITS == {
        "cja_snapshot_clean.json": 0,
        "cja_snapshot_messy.json": 2,
        "aa_snapshot_clean.json": 0,
        "aa_snapshot_messy.json": 2,
    }
    assert normalized == {
        "tool_version": "<normalized-version>",
        "overall_pct": 87,
        "categories": [{"name": "schema", "pct": 91}],
        "findings": [{"rule_id": "SCH-001"}],
        "methodology": {"paragraphs": "<normalized-copy>", "other": "preserved"},
        "distribution": {"charts": [{"label": "<normalized-copy>", "svg": "preserved"}]},
    }
    assert report["tool_version"] == "1.2.2"


def test_compatibility_fetches_only_the_public_baseline_tag(monkeypatch):
    module = _load_module()
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        stdout = f"{module.BASELINE_COMMIT}\n" if command[:2] == ["git", "rev-parse"] else ""
        return module.subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(module, "_run", fake_run)

    module._fetch_and_verify_baseline(REPO_ROOT, module._clean_environment())

    fetch = commands[0]
    assert fetch == [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "core.askPass=",
        "fetch",
        "--no-tags",
        "--force",
        module.PUBLIC_REMOTE,
        "+refs/tags/v1.2.2:refs/tags/v1.2.2",
    ]
    assert "--tags" not in fetch


def test_compatibility_allows_dev_only_lock_drift():
    module = _load_module()
    assert not hasattr(module, "_verify_lock_identity")


def test_readme_command_contract_replaces_only_argv_zero(tmp_path):
    module = _load_module()
    (tmp_path / "README.md").write_text(
        f"```bash\n{module.README_COMMAND}\n```\n",
        encoding="utf-8",
    )

    arguments = module._readme_arguments(tmp_path)

    assert arguments == [
        "sdr-grader",
        "cja_snapshot_clean.json",
        "--output",
        "grade.html",
        "--json",
        "grade.json",
        "--quiet",
    ]
    replacement = ["/isolated/bin/sdr-grader", *arguments[1:]]
    assert replacement[1:] == arguments[1:]


def test_grade_matrix_exercises_every_fixture_and_threshold_exit(tmp_path, monkeypatch):
    module = _load_module()
    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    for filename in module.FIXTURE_FAIL_BELOW_A_EXITS:
        payload = {}
        if filename.startswith("cja_"):
            identity = "messy" if "messy" in filename else "clean"
            payload = {
                "data_view": {
                    "data_view_id": identity,
                    "data_view_name": identity,
                },
                "metadata": {
                    "Data View ID": identity,
                    "Data View Name": identity,
                },
            }
        (fixture_root / filename).write_text(json.dumps(payload), encoding="utf-8")

    observed_console_commands: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd, env=None, capture=False):
        if command[0].endswith("sdr-grader"):
            observed_console_commands.append((command, Path(cwd)))
            json_path = Path(cwd) / command[command.index("--json") + 1]
            html_path = Path(cwd) / command[command.index("--output") + 1]
            payload = {
                "schema_version": 1,
                "tool_version": "1.2.2",
                "overall_pct": 47,
                "findings": [],
                "categories": [],
                "methodology": {"paragraphs": []},
                "distribution": None,
            }
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            html_path.write_text("<!doctype html>", encoding="utf-8")
            threshold = "--fail-below" in command
            messy = "messy" in command[1]
            returncode = 2 if threshold and messy else 0
            return module.subprocess.CompletedProcess(command, returncode, "", "")
        if "build_trend_report" in command[-2]:
            reports = [
                {
                    "schema_version": 1,
                    "tool_version": "1.2.2",
                    "overall_pct": score,
                    "findings": [],
                    "categories": [],
                    "methodology": {"paragraphs": []},
                    "distribution": None,
                }
                for score in (100, 47)
            ]
            trend = {
                "schema_version": 1,
                "instance_id": "trend",
                "platform": "cja",
                "points": [
                    {"timestamp": f"2026-01-0{index}", "report": report}
                    for index, report in enumerate(reports, start=1)
                ],
            }
            return module.subprocess.CompletedProcess(command, 0, json.dumps(trend), "")
        return module.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "_run", fake_run)

    results = module._run_grades(
        environment_root=tmp_path / "env",
        environment={},
        work_root=tmp_path / "output",
        fixture_root=fixture_root,
        readme_arguments=module.README_COMMAND.split(),
    )

    matrix = results["fixtures"]
    assert set(matrix) == set(module.FIXTURE_FAIL_BELOW_A_EXITS)
    for filename, expected_exit in module.FIXTURE_FAIL_BELOW_A_EXITS.items():
        assert matrix[filename]["normal_exit"] == 0
        assert matrix[filename]["fail_below_a_exit"] == expected_exit
    fixture_commands = [
        command for command, cwd in observed_console_commands if "fixture-matrix" in cwd.parts
    ]
    assert len(fixture_commands) == 8
    assert sum("--fail-below" in command for command in fixture_commands) == 4

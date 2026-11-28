"""Adapter for the shared cases of the Adobe credentials standard, version 1.

sdr-grader never reads an Adobe credential. In the ``--dataview`` and
``--rsid`` modes it starts a generator child, and the child looks up the
credential. So only two kinds of shared case can run here:

- the profile name cases, against the check that ``--profile`` uses
- the child process case, against the arguments the child receives

Every other case is skipped for a reason this module can state, and the test
run fails when a case has no such reason. The copied files are in
``tests/standard_cases``. ``known-differences.json`` at the repo root lists
the rules that do not apply.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from sdr_grader.cli.exit_codes import RUNTIME_ERROR
from sdr_grader.cli.main import main
from sdr_grader.input import shell_out

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = Path(__file__).resolve().parent / "standard_cases"
KNOWN_DIFFERENCES = json.loads((REPO_ROOT / "known-differences.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((CASES_DIR / "fixtures.json").read_text(encoding="utf-8"))
CODES = json.loads((CASES_DIR / "codes-v1.json").read_text(encoding="utf-8"))

TOOL = "sdr-grader"
# sdr-grader runs both generators, so a case for either product applies.
PRODUCTS = {"aa", "cja"}
# Commands of the standard that sdr-grader does not have, with the rule that
# known-differences.json must list as not applicable.
ABSENT_COMMANDS = {"config_check": "L2.4", "live_test": "L2.5"}
CREDENTIAL_VARIABLES = {
    "org_id": "ORG_ID",
    "client_id": "CLIENT_ID",
    "secret": "SECRET",
    "scopes": "SCOPES",
}
# The cases that this adapter runs. The list is written out so that a change
# in the shared cases cannot silently change what is tested here.
EXPECTED_RUN = {f"name-{number:03d}" for number in range(1, 13)} | {"mask-009"}


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("cases"), list):
            cases.extend(document["cases"])
    return cases


ALL_CASES = _load_cases()
NOT_APPLICABLE = {entry["rule"] for entry in KNOWN_DIFFERENCES["not_applicable"]}
LISTED_FAILURES = {
    case_id
    for difference in KNOWN_DIFFERENCES["differences"]
    for case_id in difference.get("cases", [])
}


def _is_profile_name_case(case: dict) -> bool:
    # Some file permission cases also give a profile name, so look at what the
    # case expects.
    return "profile_name" in case.get("given", {}) and "valid" in case.get("expect", {})


def _skip_reason(case: dict) -> str | None:
    """Return why sdr-grader skips the case, or None when the case runs."""
    if "tools" in case and TOOL not in case["tools"]:
        return "the case is for other tools"
    if "products" in case and not PRODUCTS & set(case["products"]):
        return "the case is for another product"
    given = case.get("given", {})
    command = given.get("command")
    if command in ABSENT_COMMANDS:
        rule = ABSENT_COMMANDS[command]
        assert rule in NOT_APPLICABLE, f"{rule} must be listed as not applicable"
        return f"sdr-grader has no {command} command"
    if command == "run_child" or _is_profile_name_case(case):
        return None
    if case["rule"] in NOT_APPLICABLE:
        return f"{case['rule']} does not apply to sdr-grader"
    raise AssertionError(f"case {case['id']} is not run and has no reason to be skipped")


RUN_CASES = [case for case in ALL_CASES if _skip_reason(case) is None]


class _FakeChild:
    """A finished child process that wrote one empty JSON snapshot."""

    def __init__(self, cmd: list[str]) -> None:
        self.stdout = io.BytesIO(b"{}")
        self.stderr = io.BytesIO(b"")
        self.returncode = 0
        self.pid = 999_999
        if "--output-dir" in cmd:
            output_dir = Path(cmd[cmd.index("--output-dir") + 1])
            (output_dir / "snapshot.json").write_bytes(b"{}")

    def poll(self) -> int:
        return self.returncode

    def wait(self) -> int:
        return self.returncode


def _child_commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Run both generator modes, with and without a profile, and return each command."""
    commands: list[list[str]] = []

    def fake_popen(cmd, **_options):
        commands.append(list(cmd))
        return _FakeChild(cmd)

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)
    for profile in (None, "client-a"):
        shell_out.shell_cja("dv_test", profile=profile)
        shell_out.shell_aa("test.rsid", profile=profile)
    assert len(commands) == 4
    return commands


def _run_case(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    given = case["given"]
    expect = case["expect"]
    if _is_profile_name_case(case):
        assert shell_out.is_valid_profile_name(given["profile_name"]) is expect["valid"]
        return
    assert given["command"] == "run_child"
    assert expect == {"child_arguments_exclude_secret": True}
    credential = FIXTURES["credentials"][given["sources"]["environment"]["credential"]]
    for field, variable in CREDENTIAL_VARIABLES.items():
        monkeypatch.setenv(variable, credential[field])
    for command in _child_commands(monkeypatch):
        for argument in command:
            for field in CREDENTIAL_VARIABLES:
                assert credential[field] not in argument


def test_the_adapter_runs_exactly_the_cases_that_apply() -> None:
    assert {case["id"] for case in RUN_CASES} == EXPECTED_RUN
    assert len({case["id"] for case in ALL_CASES}) == len(ALL_CASES)


def test_listed_cases_exist_in_the_shared_cases() -> None:
    assert {case["id"] for case in ALL_CASES} >= LISTED_FAILURES


@pytest.mark.parametrize("case", RUN_CASES, ids=[case["id"] for case in RUN_CASES])
def test_shared_case(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    """A case passes unless known-differences.json lists it, and then it must fail."""
    if case["id"] not in LISTED_FAILURES:
        _run_case(case, monkeypatch)
        return
    try:
        _run_case(case, monkeypatch)
    except AssertionError:
        return
    pytest.fail(f"{case['id']} passes now. Remove it from known-differences.json.")


@pytest.mark.parametrize(
    "case",
    [case for case in ALL_CASES if _is_profile_name_case(case)],
    ids=lambda case: case["id"],
)
def test_profile_name_cases_through_the_cli(case, tmp_path, capsys, monkeypatch) -> None:
    """The CLI rejects each invalid name before it starts a child."""
    import sdr_grader.cli.main as cli_main

    name = case["given"]["profile_name"]
    calls: list[dict] = []

    def fake_shell_cja(dataview_id, **options):
        calls.append(options)
        raise shell_out.InvalidSnapshotError("stop after the child call")

    monkeypatch.setattr(cli_main, "shell_cja", fake_shell_cja)
    monkeypatch.chdir(tmp_path)

    rc = main(["--dataview", "dv_test", "--profile", name])

    err = capsys.readouterr().err
    assert rc == RUNTIME_ERROR
    if case["expect"]["valid"]:
        assert calls == [{"profile": name}]
    else:
        assert calls == []
        if name:
            assert "[invalid_profile_name]" in err
            assert name not in err
        else:
            assert err == "error: --profile requires a non-empty value\n"


def test_the_invalid_name_code_is_a_code_of_the_standard() -> None:
    assert "invalid_profile_name" in CODES["errors"]


def test_known_differences_file_has_the_shape_of_the_standard() -> None:
    """A small check of the keys and types in known-differences-v1.schema.json."""
    schema = json.loads(
        (CASES_DIR / "known-differences-v1.schema.json").read_text(encoding="utf-8")
    )
    document = KNOWN_DIFFERENCES
    assert set(schema["required"]) <= set(document)
    assert set(document) <= set(schema["properties"])
    assert document["spec"] == schema["properties"]["spec"]["const"]
    assert document["tool"] == TOOL
    assert isinstance(document["tool_version"], str)

    for entry in document["not_applicable"]:
        assert set(entry) == {"rule", "reason"}
        assert all(isinstance(value, str) and value for value in entry.values())
    rules = [entry["rule"] for entry in document["not_applicable"]]
    assert len(rules) == len(set(rules))

    difference_shape = schema["properties"]["differences"]["items"]
    for entry in document["differences"]:
        assert set(difference_shape["required"]) <= set(entry)
        assert set(entry) <= set(difference_shape["properties"])
        assert re.fullmatch(difference_shape["properties"]["rule"]["pattern"], entry["rule"])
        assert isinstance(entry["summary"], str)
        assert all(isinstance(case_id, str) for case_id in entry.get("cases", []))
        assert isinstance(entry.get("planned", ""), str)


def test_copied_cases_match_their_recorded_checksums() -> None:
    import hashlib

    source = json.loads((CASES_DIR / "SOURCE.json").read_text(encoding="utf-8"))
    present = {path.name for path in CASES_DIR.glob("*.json")} - {"SOURCE.json"}
    assert present == set(source["files"])
    for name, checksum in source["files"].items():
        assert hashlib.sha256((CASES_DIR / name).read_bytes()).hexdigest() == checksum

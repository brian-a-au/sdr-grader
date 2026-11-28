"""Tests for ``--profile`` and for what the generator child receives.

sdr-grader reads no Adobe credential. The generator child looks it up, so
these tests pin three things: the child's command is unchanged without
``--profile``, the child keeps the environment and the working folder it needs
for its lookup, and a failed child names the generator's ``--profile-test``.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest

import sdr_grader.cli.main as cli_main
from sdr_grader.cli.exit_codes import RUNTIME_ERROR, SUCCESS
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.input import shell_out

FIXTURES = Path(__file__).parent / "fixtures"
CREDENTIAL = json.loads(
    (Path(__file__).parent / "standard_cases" / "fixtures.json").read_text(encoding="utf-8")
)["credentials"]["A"]
INVALID_NAME_ERROR = (
    "error: invalid profile name [invalid_profile_name]: a --profile name holds "
    "letters, digits, dots, underscores and hyphens only, starts with a letter "
    "or a digit, and is 64 characters or fewer\n"
)


class _FakeChild:
    def __init__(self, cmd: list[str], *, returncode: int = 0, stderr: bytes = b"") -> None:
        self.stdout = io.BytesIO(b"{}")
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.pid = 999_999
        if "--output-dir" in cmd:
            output_dir = Path(cmd[cmd.index("--output-dir") + 1])
            (output_dir / "snapshot.json").write_bytes(b"{}")

    def poll(self) -> int:
        return self.returncode

    def wait(self) -> int:
        return self.returncode


def _capture_popen(monkeypatch: pytest.MonkeyPatch, **child_options) -> list[dict]:
    calls: list[dict] = []

    def fake_popen(cmd, **options):
        calls.append({"cmd": list(cmd), "options": options})
        return _FakeChild(cmd, **child_options)

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)
    return calls


# ---------------------------------------------------------------------------
# The child's command
# ---------------------------------------------------------------------------


def test_cja_child_command_without_profile_is_unchanged(monkeypatch) -> None:
    calls = _capture_popen(monkeypatch)

    shell_out.shell_cja("dv_test")

    cmd = calls[0]["cmd"]
    assert cmd == [
        "/usr/bin/cja_auto_sdr",
        "dv_test",
        "--format",
        "json",
        "--output-dir",
        cmd[5],
        "--include-all-inventory",
        "--quiet",
    ]


def test_aa_child_command_without_profile_is_unchanged(monkeypatch) -> None:
    calls = _capture_popen(monkeypatch)

    shell_out.shell_aa("test.rsid")

    assert calls[0]["cmd"] == [
        "/usr/bin/aa_auto_sdr",
        "test.rsid",
        "--format",
        "json",
        "--output",
        "-",
    ]


def test_cja_child_gets_the_profile_after_the_extra_args(monkeypatch) -> None:
    calls = _capture_popen(monkeypatch)

    shell_out.shell_cja("dv_test", extra_args=["--log-level", "debug"], profile="client-a")

    assert calls[0]["cmd"][6:] == [
        "--include-all-inventory",
        "--quiet",
        "--log-level",
        "debug",
        "--profile",
        "client-a",
    ]


def test_aa_child_gets_the_profile_after_the_extra_args(monkeypatch) -> None:
    calls = _capture_popen(monkeypatch)

    shell_out.shell_aa("test.rsid", extra_args=["--company", "acme"], profile="client-a.eu_west")

    assert calls[0]["cmd"] == [
        "/usr/bin/aa_auto_sdr",
        "test.rsid",
        "--format",
        "json",
        "--output",
        "-",
        "--company",
        "acme",
        "--profile",
        "client-a.eu_west",
    ]


@pytest.mark.parametrize("shell", [shell_out.shell_cja, shell_out.shell_aa])
@pytest.mark.parametrize("name", ["../other", "-x", "--config", "a b", "a\x1bb", "", "é"])
def test_shell_functions_reject_an_invalid_profile_before_spawning(
    monkeypatch, shell, name
) -> None:
    calls = _capture_popen(monkeypatch)

    with pytest.raises(InvalidSnapshotError, match=r"\[invalid_profile_name\]") as raised:
        shell("dv_test", profile=name)

    assert calls == []
    if name:
        assert name not in str(raised.value)


@pytest.mark.parametrize("name", [None, 7, b"prod", ["prod"]])
def test_profile_name_check_rejects_values_that_are_not_text(name) -> None:
    assert shell_out.is_valid_profile_name(name) is False


def test_profile_name_check_rejects_a_trailing_newline() -> None:
    assert shell_out.is_valid_profile_name("prod\n") is False


# ---------------------------------------------------------------------------
# The CLI option
# ---------------------------------------------------------------------------


def test_help_documents_profile(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "--profile NAME" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("mode_flag", "shell_name", "fixture"),
    [
        ("--dataview", "shell_cja", "cja_snapshot_clean.json"),
        ("--rsid", "shell_aa", "aa_snapshot_messy.json"),
    ],
)
@pytest.mark.parametrize("profile_args", [[], ["--profile", "client-a"]])
def test_cli_passes_profile_only_when_given(
    tmp_path, monkeypatch, mode_flag, shell_name, fixture, profile_args
) -> None:
    payload = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    calls: list[tuple] = []

    def fake_shell(identifier, **options):
        calls.append((identifier, options))
        return payload, f"shell-out:{shell_name}"

    monkeypatch.setattr(cli_main, shell_name, fake_shell)

    rc = main(
        [mode_flag, "some.id", *profile_args, "--output", str(tmp_path / "out.html"), "--quiet"]
    )

    assert rc == SUCCESS
    expected_options = {"profile": "client-a"} if profile_args else {}
    assert calls == [("some.id", expected_options)]


def _no_shell_out(*_args, **_kwargs):
    raise AssertionError("the option must be rejected before a child is started")


@pytest.mark.parametrize(
    "inputs",
    [
        [str(FIXTURES / "cja_snapshot_clean.json")],
        ["-"],
        [str(FIXTURES)],
        [str(FIXTURES), "--trend"],
        [],
    ],
)
def test_cli_rejects_profile_outside_the_generator_modes(
    tmp_path, capsys, monkeypatch, inputs
) -> None:
    monkeypatch.setattr(cli_main, "shell_aa", _no_shell_out)
    monkeypatch.setattr(cli_main, "shell_cja", _no_shell_out)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.chdir(tmp_path)

    rc = main([*inputs, "--profile", "client-a"])

    assert rc == RUNTIME_ERROR
    assert capsys.readouterr().err == "error: --profile requires --dataview or --rsid\n"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mode", [["--dataview", "dv_test"], ["--rsid", "test.rsid"]])
@pytest.mark.parametrize("name", ["../other", "-x", "a/b", "a" * 65, "bad\x1b[31mname"])
def test_cli_rejects_an_invalid_profile_name_before_spawning(
    tmp_path, capsys, monkeypatch, mode, name
) -> None:
    calls = _capture_popen(monkeypatch)
    monkeypatch.chdir(tmp_path)

    rc = main([*mode, f"--profile={name}"])

    assert rc == RUNTIME_ERROR
    assert capsys.readouterr().err == INVALID_NAME_ERROR
    assert calls == []
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# The hint when the child fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shell", "tool"),
    [(shell_out.shell_cja, "cja_auto_sdr"), (shell_out.shell_aa, "aa_auto_sdr")],
)
@pytest.mark.parametrize(
    ("profile", "command_name"),
    [("client-a", "client-a"), (None, "NAME")],
)
def test_failed_child_names_the_generator_profile_test(
    monkeypatch, shell, tool, profile, command_name
) -> None:
    _capture_popen(monkeypatch, returncode=2, stderr=b"PRIVATE auth token expired")

    with pytest.raises(InvalidSnapshotError) as raised:
        shell("some.id", profile=profile)

    assert str(raised.value) == (
        f"shell error [child-exit]: {tool} returned status 2. "
        f"The error output of {tool} is hidden. To test the credential of a "
        f"profile, run: {tool} --profile-test {command_name}"
    )


def test_cli_prints_the_profile_test_hint_on_stderr_only(tmp_path, capsys, monkeypatch) -> None:
    _capture_popen(monkeypatch, returncode=1, stderr=b"PRIVATE auth token expired")
    monkeypatch.chdir(tmp_path)

    rc = main(["--rsid", "test.rsid", "--profile", "client-a"])

    captured = capsys.readouterr()
    assert rc == RUNTIME_ERROR
    assert captured.out == ""
    assert captured.err == (
        "error: shell error [child-exit]: aa_auto_sdr returned status 1. "
        "The error output of aa_auto_sdr is hidden. To test the credential of a "
        "profile, run: aa_auto_sdr --profile-test client-a\n"
    )
    assert "PRIVATE" not in captured.err


# ---------------------------------------------------------------------------
# What the child inherits
# ---------------------------------------------------------------------------

_INHERITED = (
    "ORG_ID",
    "CLIENT_ID",
    "SECRET",
    "SCOPES",
    "AA_PROFILE",
    "CJA_PROFILE",
    "PATH",
    "HOME",
)


@pytest.mark.parametrize("platform_name", ["posix", "nt"])
def test_popen_options_leave_the_environment_and_working_folder_alone(platform_name) -> None:
    options = shell_out._popen_options(platform_name)  # noqa: SLF001

    assert "env" not in options
    assert "cwd" not in options


@pytest.mark.parametrize(
    ("shell", "profile"),
    [
        (shell_out.shell_cja, None),
        (shell_out.shell_cja, "client-a"),
        (shell_out.shell_aa, None),
        (shell_out.shell_aa, "client-a"),
    ],
)
def test_generator_calls_pass_no_environment_or_working_folder(monkeypatch, shell, profile) -> None:
    calls = _capture_popen(monkeypatch)

    shell("some.id", profile=profile)

    assert "env" not in calls[0]["options"]
    assert "cwd" not in calls[0]["options"]


def test_real_child_keeps_the_lookup_variables_path_and_working_folder(
    tmp_path, monkeypatch
) -> None:
    """Start a real child process and read back what it inherited."""
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    monkeypatch.setenv("ORG_ID", CREDENTIAL["org_id"])
    monkeypatch.setenv("CLIENT_ID", CREDENTIAL["client_id"])
    monkeypatch.setenv("SECRET", CREDENTIAL["secret"])
    monkeypatch.setenv("SCOPES", CREDENTIAL["scopes"])
    monkeypatch.setenv("AA_PROFILE", "aa-profile")
    monkeypatch.setenv("CJA_PROFILE", "cja-profile")
    expected = {name: os.environ[name] for name in _INHERITED}
    monkeypatch.setattr(shell_out.shutil, "which", lambda _tool: sys.executable)
    code = (
        "import json,os;"
        f"print(json.dumps({{'env': {{n: os.environ.get(n) for n in {_INHERITED!r}}},"
        "'cwd': os.getcwd()}))"
    )

    seen, _source = shell_out._shell_out(  # noqa: SLF001 - exercise the process boundary
        "fake_snapshot_tool",
        ["-c", code],
        flag="--fake",
    )

    assert seen["env"] == expected
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(work)

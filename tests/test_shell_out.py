"""Privacy and lifecycle tests for upstream snapshot-tool execution."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.input import shell_out

STDOUT_CANARY = "PRIVATE-STDOUT-CANARY"
STDERR_CANARY = "PRIVATE-STDERR-CANARY"
ARGV_CANARY = "PRIVATE-ARGV-CANARY"
PATH_CANARY = "/private/customer/PRIVATE-PATH-CANARY.json"
CONTROL_CANARY = "\x1b]8;;file:///private/customer\x07PRIVATE-CONTROL-CANARY\x1b]8;;\x07"


def _run_python(monkeypatch: pytest.MonkeyPatch, code: str) -> tuple[dict, str]:
    monkeypatch.setattr(shell_out.shutil, "which", lambda _tool: sys.executable)
    return shell_out._shell_out(  # noqa: SLF001 - exercise the process boundary
        "fake_snapshot_tool",
        ["-c", code, ARGV_CANARY],
        flag="--fake",
    )


def _assert_private_values_absent(text: str) -> None:
    for canary in (
        STDOUT_CANARY,
        STDERR_CANARY,
        ARGV_CANARY,
        PATH_CANARY,
        "PRIVATE-CONTROL-CANARY",
        "\x1b",
        "\x07",
    ):
        assert canary not in text


def test_shell_out_returns_object_without_private_provenance(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot, source = _run_python(
        monkeypatch,
        (
            "import json,sys;"
            f"sys.stderr.write({(STDERR_CANARY + CONTROL_CANARY + PATH_CANARY)!r});"
            "print(json.dumps({'metadata': {'Data View ID': 'dv'}}))"
        ),
    )

    assert snapshot == {"metadata": {"Data View ID": "dv"}}
    assert source == "shell-out:fake_snapshot_tool"
    diagnostics = capsys.readouterr().err
    assert diagnostics == (
        "warning [shell-child-diagnostics]: "
        "fake_snapshot_tool emitted diagnostics; content suppressed\n"
    )
    _assert_private_values_absent(diagnostics + source)


def test_shell_out_nonzero_is_structural_and_value_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = (
        "import sys;"
        f"sys.stdout.write({STDOUT_CANARY!r});"
        f"sys.stderr.write({(STDERR_CANARY + CONTROL_CANARY + PATH_CANARY)!r});"
        "sys.exit(7)"
    )

    with pytest.raises(InvalidSnapshotError) as raised:
        _run_python(monkeypatch, code)

    visible = str(raised.value) + capsys.readouterr().err
    assert "shell error [child-exit]" in visible
    assert "status 7" in visible
    _assert_private_values_absent(visible)


def test_shell_out_invalid_json_hides_parser_and_child_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = (
        "import sys;"
        f"sys.stdout.write({(STDOUT_CANARY + ' {not-json')!r});"
        f"sys.stderr.write({STDERR_CANARY!r})"
    )

    with pytest.raises(InvalidSnapshotError) as raised:
        _run_python(monkeypatch, code)

    visible = str(raised.value) + capsys.readouterr().err
    assert "shell error [invalid-json]" in visible
    assert "line 1 column" not in visible
    _assert_private_values_absent(visible)


def test_shell_out_rejects_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(InvalidSnapshotError, match=r"shell error \[invalid-shape\]"):
        _run_python(monkeypatch, "print('[]')")


@pytest.mark.parametrize(
    ("limit_name", "code", "stream_name"),
    [
        ("MAX_STDOUT_BYTES", "import sys;sys.stdout.write('x' * 4096)", "stdout"),
        (
            "MAX_STDERR_BYTES",
            "import json,sys;sys.stderr.write('x' * 4096);print(json.dumps({}))",
            "stderr",
        ),
    ],
)
def test_shell_out_caps_child_streams(
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    code: str,
    stream_name: str,
) -> None:
    monkeypatch.setattr(shell_out, limit_name, 128)

    with pytest.raises(InvalidSnapshotError) as raised:
        _run_python(monkeypatch, code)

    message = str(raised.value)
    assert "shell error [output-limit]" in message
    assert stream_name in message
    assert "x" * 20 not in message


def test_shell_out_stops_child_when_stream_limit_is_crossed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shell_out, "MAX_STDOUT_BYTES", 128)
    started = time.monotonic()

    with pytest.raises(InvalidSnapshotError, match=r"shell error \[output-limit\]"):
        _run_python(
            monkeypatch,
            "import sys,time;sys.stdout.write('x' * 4096);sys.stdout.flush();time.sleep(1)",
        )

    assert time.monotonic() - started < 0.5


def test_bounded_capture_requires_both_binary_pipes() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(1)"],
        start_new_session=True,
    )

    with pytest.raises(InvalidSnapshotError, match=r"shell error \[io-failed\]"):
        shell_out._communicate_bounded(  # noqa: SLF001 - boundary failure proof
            process,
            tool="fake_snapshot_tool",
        )

    process.wait(timeout=1)


def test_shell_out_timeout_terminates_direct_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shell_out, "SHELL_OUT_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(InvalidSnapshotError, match=r"shell error \[timeout\]"):
        _run_python(monkeypatch, "import time;time.sleep(5)")


@pytest.mark.skipif(os.name != "posix", reason="process-group assertion is POSIX-specific")
def test_shell_out_timeout_terminates_descendant_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "descendant-survived"
    child_code = (
        "import pathlib,time;"
        "time.sleep(.35);"
        f"pathlib.Path({str(marker)!r}).write_text('survived')"
    )
    parent_code = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
        "time.sleep(5)"
    )
    monkeypatch.setattr(shell_out, "SHELL_OUT_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(InvalidSnapshotError, match=r"shell error \[timeout\]"):
        _run_python(monkeypatch, parent_code)

    time.sleep(0.45)
    assert not marker.exists()


def test_shell_out_invalid_utf8_is_value_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(InvalidSnapshotError) as raised:
        _run_python(monkeypatch, "import os;os.write(1, b'\\xff')")

    assert "shell error [invalid-encoding]" in str(raised.value)
    _assert_private_values_absent(str(raised.value))


def test_windows_process_options_create_a_child_group() -> None:
    options = shell_out._popen_options("nt")  # noqa: SLF001
    assert options["creationflags"] == 0x00000200
    assert "start_new_session" not in options


def test_process_tree_cleanup_falls_back_to_direct_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Process:
        pid = 123
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    process = _Process()
    monkeypatch.setattr(shell_out.os, "name", "posix")
    monkeypatch.setattr(
        shell_out.os,
        "killpg",
        lambda *_args: (_ for _ in ()).throw(ProcessLookupError()),
    )

    shell_out._terminate_process_tree(process)  # type: ignore[arg-type]  # noqa: SLF001

    assert process.killed is True


def test_non_posix_process_cleanup_kills_direct_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Process:
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    process = _Process()
    monkeypatch.setattr(shell_out.os, "name", "nt")

    shell_out._terminate_process_tree(process)  # type: ignore[arg-type]  # noqa: SLF001

    assert process.killed is True

"""Mode 3: shell out to cja_auto_sdr / aa_auto_sdr (SPEC §7).

The grader does not call Adobe APIs directly. To run against a live data
view or report suite, it shells out to the upstream snapshot tool with
`--format json --output -` and parses the captured stdout as if it were
a Mode 1 file.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError

# Upstream tools make live Adobe API calls; a stalled connection should
# fail loudly, not hang a CI job forever.
SHELL_OUT_TIMEOUT_SECONDS = 600
MAX_STDOUT_BYTES = 32 * 1024 * 1024
MAX_STDERR_BYTES = 256 * 1024


def shell_cja(
    dataview_id: str, *, extra_args: list[str] | None = None
) -> tuple[dict[str, Any], str]:
    """Shell out to cja_auto_sdr against a CJA data view ID.

    Always passes ``--include-all-inventory`` so the snapshot ships
    calculated metrics and segments alongside dimensions/metrics —
    without it, those rule packs grade against empty inputs and stay
    silent. See cja_auto_sdr's Component Inventory Overview for the
    full set of ``--include-*`` switches.
    """
    return _shell_out(
        "cja_auto_sdr",
        [
            dataview_id,
            "--include-all-inventory",
            "--format",
            "json",
            "--output",
            "-",
            *(extra_args or []),
        ],
        flag="--dataview",
    )


def shell_aa(rsid: str, *, extra_args: list[str] | None = None) -> tuple[dict[str, Any], str]:
    """Shell out to aa_auto_sdr against an AA report suite ID."""
    return _shell_out(
        "aa_auto_sdr",
        [rsid, "--format", "json", "--output", "-", *(extra_args or [])],
        flag="--rsid",
    )


def _shell_out(tool: str, argv: list[str], *, flag: str) -> tuple[dict[str, Any], str]:
    binary = shutil.which(tool)
    if not binary:
        raise InvalidSnapshotError(
            f"{tool} not found on PATH; install it before using {flag}, or "
            "pass a snapshot file path / stdin instead."
        )
    cmd = [binary, *argv]

    # This bounds and cleans up a normal child-process boundary; it is not a
    # sandbox. The invoked snapshot tool retains the OS/network authority of
    # the user who launched sdr-grader.
    popen_options = _popen_options(os.name)

    try:
        process = subprocess.Popen(cmd, **popen_options)
        stdout, stderr = process.communicate(timeout=SHELL_OUT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        process.communicate()
        raise InvalidSnapshotError(
            f"shell error [timeout]: {tool} exceeded the execution deadline"
        ) from None
    except OSError:
        raise InvalidSnapshotError(
            f"shell error [invoke-failed]: {tool} could not be started"
        ) from None

    if len(stdout) > MAX_STDOUT_BYTES:
        raise InvalidSnapshotError(
            f"shell error [output-limit]: {tool} stdout exceeded the byte limit"
        )
    if len(stderr) > MAX_STDERR_BYTES:
        raise InvalidSnapshotError(
            f"shell error [output-limit]: {tool} stderr exceeded the byte limit"
        )
    if process.returncode:
        raise InvalidSnapshotError(
            f"shell error [child-exit]: {tool} returned status {process.returncode}"
        )

    if stderr:
        print(
            f"warning [shell-child-diagnostics]: "
            f"{tool} emitted diagnostics; content suppressed",
            file=sys.stderr,
        )

    try:
        decoded = stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidSnapshotError(
            f"shell error [invalid-encoding]: {tool} stdout was not UTF-8"
        ) from None
    try:
        snapshot = json.loads(decoded)
    except json.JSONDecodeError:
        raise InvalidSnapshotError(
            f"shell error [invalid-json]: {tool} stdout was not valid JSON"
        ) from None
    if not isinstance(snapshot, dict):
        raise InvalidSnapshotError(
            f"shell error [invalid-shape]: {tool} stdout must be a JSON object"
        )
    return snapshot, f"shell-out:{tool}"


def _popen_options(platform_name: str) -> dict[str, Any]:
    options: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if platform_name == "posix":
        options["start_new_session"] = True
    elif platform_name == "nt":
        options["creationflags"] = getattr(
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0x00000200,
        )
    return options


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Best-effort termination of the child and its descendants."""
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        process.kill()

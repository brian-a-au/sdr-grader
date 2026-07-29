"""Mode 3: shell out to cja_auto_sdr / aa_auto_sdr (SPEC §7).

The grader does not call Adobe APIs directly. To run against a live data
view or report suite, it asks the upstream snapshot tool for JSON and
parses the emitted snapshot as if it were a Mode 1 file.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

from sdr_grader.core.exceptions import InvalidSnapshotError

# Upstream tools make live Adobe API calls; a stalled connection should
# fail loudly, not hang a CI job forever.
SHELL_OUT_TIMEOUT_SECONDS = 600
MAX_STDOUT_BYTES = 32 * 1024 * 1024
MAX_STDERR_BYTES = 256 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_READER_JOIN_SECONDS = 1.0


def shell_cja(
    dataview_id: str, *, extra_args: list[str] | None = None
) -> tuple[dict[str, Any], str]:
    """Shell out to cja_auto_sdr against a CJA data view ID.

    Always passes ``--include-all-inventory --quiet`` so the snapshot ships
    calculated metrics and segments alongside dimensions/metrics —
    without it, those rule packs grade against empty inputs and stay
    silent. See cja_auto_sdr's Component Inventory Overview for the full
    set of ``--include-*`` switches.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="sdr-grader-cja-") as output_dir:
            return _shell_out(
                "cja_auto_sdr",
                [
                    dataview_id,
                    "--format",
                    "json",
                    "--output-dir",
                    output_dir,
                    "--include-all-inventory",
                    "--quiet",
                    *(extra_args or []),
                ],
                flag="--dataview",
                json_output_dir=Path(output_dir),
            )
    except OSError:
        raise InvalidSnapshotError(
            "shell error [temporary-output]: cja_auto_sdr temporary output handling failed"
        ) from None


def shell_aa(rsid: str, *, extra_args: list[str] | None = None) -> tuple[dict[str, Any], str]:
    """Shell out to aa_auto_sdr against an AA report suite ID."""
    return _shell_out(
        "aa_auto_sdr",
        [rsid, "--format", "json", "--output", "-", *(extra_args or [])],
        flag="--rsid",
    )


def _shell_out(
    tool: str,
    argv: list[str],
    *,
    flag: str,
    json_output_dir: Path | None = None,
) -> tuple[dict[str, Any], str]:
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
    except OSError:
        raise InvalidSnapshotError(
            f"shell error [invoke-failed]: {tool} could not be started"
        ) from None

    stdout, stderr = _communicate_bounded(process, tool=tool)
    if process.returncode:
        raise InvalidSnapshotError(
            f"shell error [child-exit]: {tool} returned status {process.returncode}"
        )

    if stderr:
        print(
            f"warning [shell-child-diagnostics]: {tool} emitted diagnostics; content suppressed",
            file=sys.stderr,
        )

    encoded_snapshot = (
        stdout
        if json_output_dir is None
        else _read_generated_json(tool=tool, output_dir=json_output_dir)
    )
    try:
        decoded = encoded_snapshot.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidSnapshotError(
            f"shell error [invalid-encoding]: {tool} output was not UTF-8"
        ) from None
    try:
        snapshot = json.loads(decoded)
    except json.JSONDecodeError:
        raise InvalidSnapshotError(
            f"shell error [invalid-json]: {tool} output was not valid JSON"
        ) from None
    except RecursionError:
        raise InvalidSnapshotError(
            f"shell error [invalid-json-depth]: {tool} output exceeded nesting limits"
        ) from None
    if not isinstance(snapshot, dict):
        raise InvalidSnapshotError(
            f"shell error [invalid-shape]: {tool} output must be a JSON object"
        )
    return snapshot, f"shell-out:{tool}"


def _read_generated_json(*, tool: str, output_dir: Path) -> bytes:
    try:
        json_outputs = [path for path in output_dir.glob("*.json") if path.is_file()]
    except OSError:
        raise InvalidSnapshotError(
            f"shell error [output-discovery]: {tool} JSON output could not be inspected"
        ) from None
    if len(json_outputs) != 1:
        raise InvalidSnapshotError(
            f"shell error [output-count]: {tool} produced {len(json_outputs)} JSON outputs; "
            "expected exactly one"
        )
    try:
        with json_outputs[0].open("rb") as stream:
            encoded = stream.read(MAX_STDOUT_BYTES + 1)
    except (OSError, ValueError):
        raise InvalidSnapshotError(
            f"shell error [io-failed]: {tool} JSON output could not be read"
        ) from None
    if len(encoded) > MAX_STDOUT_BYTES:
        raise InvalidSnapshotError(
            f"shell error [output-limit]: {tool} JSON output exceeded the byte limit"
        )
    return encoded


def _communicate_bounded(
    process: subprocess.Popen[bytes],
    *,
    tool: str,
) -> tuple[bytes, bytes]:
    """Capture fixed-size child streams and stop the process at either limit."""
    if process.stdout is None or process.stderr is None:
        _terminate_process_tree(process)
        raise InvalidSnapshotError(f"shell error [io-failed]: {tool} output pipes were unavailable")

    buffers: dict[str, bytes] = {}
    over_limit: set[str] = set()
    read_failures: set[str] = set()
    stop_requested = threading.Event()
    state_lock = threading.Lock()

    def read_stream(name: str, stream: BinaryIO, limit: int) -> None:
        captured = bytearray()
        try:
            while True:
                remaining = limit - len(captured)
                read_size = min(_READ_CHUNK_BYTES, max(1, remaining + 1))
                chunk = stream.read(read_size)
                if not chunk:
                    break
                if len(chunk) > remaining:
                    with state_lock:
                        over_limit.add(name)
                    stop_requested.set()
                    _terminate_process_tree(process)
                    break
                captured.extend(chunk)
        except (OSError, ValueError):
            with state_lock:
                read_failures.add(name)
            stop_requested.set()
            _terminate_process_tree(process)
        finally:
            buffers[name] = bytes(captured)

    streams = (
        ("stdout", process.stdout, MAX_STDOUT_BYTES),
        ("stderr", process.stderr, MAX_STDERR_BYTES),
    )
    readers = [
        threading.Thread(
            target=read_stream,
            args=(name, stream, limit),
            name=f"sdr-grader-{name}-reader",
            daemon=True,
        )
        for name, stream, limit in streams
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + SHELL_OUT_TIMEOUT_SECONDS
    timed_out = False
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _terminate_process_tree(process)
            break
        if stop_requested.wait(min(0.05, remaining)):
            _terminate_process_tree(process)
            break

    try:
        process.wait()
    except OSError:
        _terminate_process_tree(process)
        raise InvalidSnapshotError(
            f"shell error [io-failed]: {tool} process status was unavailable"
        ) from None

    for reader in readers:
        reader.join(timeout=_READER_JOIN_SECONDS)
    readers_still_alive = any(reader.is_alive() for reader in readers)
    for _name, stream, _limit in streams:
        stream.close()
    if readers_still_alive:
        for reader in readers:
            reader.join(timeout=0.1)
    if any(reader.is_alive() for reader in readers):
        raise InvalidSnapshotError(f"shell error [io-failed]: {tool} output pipes did not close")
    if timed_out:
        raise InvalidSnapshotError(f"shell error [timeout]: {tool} exceeded the execution deadline")
    if over_limit:
        stream_name = "stdout" if "stdout" in over_limit else "stderr"
        raise InvalidSnapshotError(
            f"shell error [output-limit]: {tool} {stream_name} exceeded the byte limit"
        )
    if read_failures:
        raise InvalidSnapshotError(f"shell error [io-failed]: {tool} output could not be captured")
    return buffers["stdout"], buffers["stderr"]


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
    except OSError:
        with contextlib.suppress(OSError):
            process.kill()

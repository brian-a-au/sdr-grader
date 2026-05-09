"""Mode 3: shell out to cja_auto_sdr / aa_auto_sdr (SPEC §7).

The grader does not call Adobe APIs directly. To run against a live data
view or report suite, it shells out to the upstream snapshot tool with
`--format json --output -` and parses the captured stdout as if it were
a Mode 1 file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError


def shell_cja(
    dataview_id: str, *, extra_args: list[str] | None = None
) -> tuple[dict[str, Any], str]:
    """Shell out to cja_auto_sdr against a CJA data view ID."""
    return _shell_out(
        "cja_auto_sdr",
        [dataview_id, "--format", "json", "--output", "-", *(extra_args or [])],
        flag="--dataview",
    )


def shell_aa(
    rsid: str, *, extra_args: list[str] | None = None
) -> tuple[dict[str, Any], str]:
    """Shell out to aa_auto_sdr against an AA report suite ID."""
    return _shell_out(
        "aa_auto_sdr",
        [rsid, "--format", "json", "--output", "-", *(extra_args or [])],
        flag="--rsid",
    )


def _shell_out(
    tool: str, argv: list[str], *, flag: str
) -> tuple[dict[str, Any], str]:
    binary = shutil.which(tool)
    if not binary:
        raise InvalidSnapshotError(
            f"{tool} not found on PATH; install it before using {flag}, or "
            "pass a snapshot file path / stdin instead."
        )
    cmd = [binary, *argv]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        raise InvalidSnapshotError(
            f"{tool} exited {exc.returncode}: {stderr.strip() or '(no stderr)'}"
        ) from exc
    except FileNotFoundError as exc:
        raise InvalidSnapshotError(f"{tool} could not be invoked: {exc}") from exc

    try:
        snapshot = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidSnapshotError(
            f"{tool} produced output that is not valid JSON: {exc}"
        ) from exc
    return snapshot, f"shell-out:{tool} {argv[0]}"

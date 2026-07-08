"""Input loading for all four CLI modes (SPEC §7).

- Mode 1: file path -> read JSON.
- Mode 2: directory path -> pick the latest snapshot in it, or `--at` to
  pick the closest one not after a target timestamp.
- Mode 3: shell out to cja_auto_sdr / aa_auto_sdr (handled in shell_out.py).
- Mode 4: stdin -> read sys.stdin.

Returns (parsed_snapshot, source_label) so the adapter and downstream
methodology can record where the data came from.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.timeparse import parse_timestamp

STDIN_TOKEN = "-"

# Filename timestamp pattern: snapshot_2026-04-25T09-14-00.json or similar.
_TIMESTAMP_RE = re.compile(
    r"(?P<year>\d{4})[-_](?P<month>\d{2})[-_](?P<day>\d{2})"
    r"(?:[T_-](?P<hour>\d{2})[-_:](?P<minute>\d{2})(?:[-_:](?P<second>\d{2}))?)?"
)


def load_snapshot(
    path_or_token: str, *, at: str | None = None
) -> tuple[dict[str, Any], str]:
    """Read and parse a snapshot from a file path, directory, or stdin token.

    Returns (parsed_snapshot, source_label).
    """
    if path_or_token == STDIN_TOKEN:
        return _load_stdin()
    p = Path(path_or_token)
    if p.is_dir():
        return _load_from_directory(p, at=at)
    if p.is_file():
        return _load_from_file(p)
    raise InvalidSnapshotError(f"snapshot path not found: {path_or_token}")


def _load_stdin() -> tuple[dict[str, Any], str]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise InvalidSnapshotError("stdin is empty; expected JSON snapshot")
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidSnapshotError(f"stdin is not valid JSON: {exc}") from exc
    return snapshot, "stdin"


def _load_from_file(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidSnapshotError(f"could not read {path}: {exc}") from exc
    try:
        snapshot = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidSnapshotError(f"{path}: not valid JSON: {exc}") from exc
    return snapshot, str(path)


def _load_from_directory(
    directory: Path, *, at: str | None
) -> tuple[dict[str, Any], str]:
    candidates = sorted(directory.glob("*.json"))
    if not candidates:
        raise InvalidSnapshotError(f"no .json snapshots found in {directory}")
    chosen = _pick_snapshot(candidates, at=at)
    return _load_from_file(chosen)


def _pick_snapshot(
    candidates: list[Path], *, at: str | None
) -> Path:
    """Pick a single snapshot file from a directory.

    Without `at`: use the most recent by extracted timestamp, falling back
    to mtime when filenames don't carry one.
    With `at`: use the snapshot closest to (and not after) the target.
    """
    annotated: list[tuple[Path, datetime | None]] = [
        (p, _extract_timestamp(p)) for p in candidates
    ]
    has_timestamp = [(p, ts) for p, ts in annotated if ts is not None]
    if not has_timestamp:
        # Fall back to filesystem mtime — deterministic across runs on the
        # same machine, even if not portable.
        annotated_mtime = [
            (p, datetime.fromtimestamp(p.stat().st_mtime)) for p in candidates
        ]
        has_timestamp = annotated_mtime

    if at is None:
        return max(has_timestamp, key=lambda pair: pair[1])[0]

    target = _parse_iso_timestamp(at)
    if target is None:
        raise InvalidSnapshotError(
            f"--at value {at!r} is not a recognized timestamp; "
            "use ISO-8601 (e.g. 2026-04-25 or 2026-04-25T09:14)."
        )
    not_after = [(p, ts) for p, ts in has_timestamp if ts <= target]
    if not_after:
        return max(not_after, key=lambda pair: pair[1])[0]
    raise InvalidSnapshotError(
        f"no snapshot in directory is at or before {at!r}"
    )


def _extract_timestamp(path: Path) -> datetime | None:
    match = _TIMESTAMP_RE.search(path.stem)
    if not match:
        return None
    parts = match.groupdict()
    try:
        year = int(parts["year"])
        month = int(parts["month"])
        day = int(parts["day"])
        hour = int(parts["hour"] or 0)
        minute = int(parts["minute"] or 0)
        second = int(parts["second"] or 0)
        return datetime(year, month, day, hour, minute, second)
    except (TypeError, ValueError):
        return None


def _parse_iso_timestamp(value: str) -> datetime | None:
    # Filename-derived timestamps are naive, so --at comparisons happen
    # on naive UTC values; slashes tolerate 2026/04/25-style input.
    parsed = parse_timestamp(value.replace("/", "-"))
    if parsed is None:
        return None
    return parsed.replace(tzinfo=None)

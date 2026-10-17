#!/usr/bin/env python3
"""Drive release-soak observations from outside GitHub's best-effort cron.

Each invocation is one tick: list recent main runs, dispatch a new run when
none is pending and the newest is old enough, and flag a long gap without a
successful observation. Exit 0 is OK, 2 an alert, 1 a gh failure.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

WORKFLOW = "release-soak.yml"
PENDING_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})
OBSERVATION_EVENTS = frozenset({"schedule", "workflow_dispatch"})
FIELDS = "databaseId,status,conclusion,createdAt,updatedAt,event,headBranch"


@dataclass(frozen=True)
class Decision:
    dispatch: bool
    alert: str | None


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def decide(
    runs: list[dict[str, str]],
    now: datetime,
    *,
    interval_seconds: int = 1800,
    alert_after_seconds: int = 10800,
) -> Decision:
    main_runs = [r for r in runs if r.get("headBranch") == "main"]
    pending = any(r.get("status") != "completed" for r in main_runs)
    dispatch = not pending
    if dispatch and main_runs:
        newest = max(_parse(r["createdAt"]) for r in main_runs)
        dispatch = (now - newest).total_seconds() >= interval_seconds
    successes = [
        _parse(r["updatedAt"])
        for r in main_runs
        if r.get("conclusion") == "success" and r.get("event") in OBSERVATION_EVENTS
    ]
    alert = None
    if not successes:
        alert = "no successful observation in listed history"
    else:
        age = (now - max(successes)).total_seconds()
        if age > alert_after_seconds:
            alert = f"no successful observation in {int(age // 60)} minutes"
    return Decision(dispatch, alert)


def _gh(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return result if result.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notify", action="store_true", help="macOS notification on alert")
    parser.add_argument("--dry-run", action="store_true", help="print the decision only")
    args = parser.parse_args(argv)

    listed = _gh(
        ["gh", "run", "list", "--workflow", WORKFLOW, "--branch", "main",
         "--limit", "20", "--json", FIELDS]
    )  # fmt: skip
    try:
        runs = json.loads(listed.stdout) if listed else None
    except json.JSONDecodeError:
        runs = None
    if not isinstance(runs, list):
        print("release soak driver: could not list runs with gh", file=sys.stderr)
        return 1

    decision = decide(runs, datetime.now(UTC))
    print(f"dispatch={decision.dispatch} alert={decision.alert or 'none'}")
    dispatch_failed = (
        decision.dispatch
        and not args.dry_run
        and _gh(["gh", "workflow", "run", WORKFLOW, "--ref", "main"]) is None
    )
    if dispatch_failed:
        print("release soak driver: could not dispatch with gh", file=sys.stderr)
        return 1
    if decision.alert:
        if args.notify and sys.platform == "darwin":
            script = f'display notification "{decision.alert}" with title "sdr-grader soak"'
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

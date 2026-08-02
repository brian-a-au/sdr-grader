#!/usr/bin/env python3
"""Verify a release-soak timeline and emit its final evidence and GO comment."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

OWNER_LOGIN = "brian-a-au"
PRIVATE_CLEAR_MARKER = "sdr-grader-v1.2.1-private-advisory-clear"
GO_MARKER = "sdr-grader-v1.2.1-announcement-go"
MAX_GAP_SECONDS = 14_400
CHECKPOINT_TOLERANCE_SECONDS = 7_200


class VerificationError(Exception):
    """The soak timeline does not support an announcement GO."""


def _epoch(value: str) -> int:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp())


def _iso(value: int) -> str:
    return dt.datetime.fromtimestamp(value, tz=dt.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _workflow_runs(payload: Any) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    runs: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(
            page.get("workflow_runs"), list
        ):
            raise VerificationError("workflow-runs response has an invalid shape")
        runs.extend(page["workflow_runs"])
    return runs


def _comments(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list) and (
        not payload or all(isinstance(item, dict) for item in payload)
    ):
        return payload
    pages = payload if isinstance(payload, list) else [payload]
    comments: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, list):
            raise VerificationError("comments response has an invalid shape")
        comments.extend(page)
    return comments


def _maintainer_comment(
    comments: list[dict[str, Any]],
    marker: str,
    *,
    not_before: int,
) -> dict[str, Any] | None:
    matches = [
        comment
        for comment in comments
        if marker in str(comment.get("body", ""))
        and comment.get("author_association") == "OWNER"
        and comment.get("user", {}).get("login") == OWNER_LOGIN
        and _epoch(str(comment.get("created_at"))) >= not_before
    ]
    return sorted(matches, key=lambda item: str(item["created_at"]))[-1] if matches else None


def verify_timeline(
    *,
    runs_payload: Any,
    current_run: dict[str, Any],
    comments_payload: Any,
    start_epoch: int,
    end_epoch: int,
    start_url: str,
    release: str,
    release_commit: str,
    companion: str,
    finalized_epoch: int | None = None,
) -> tuple[dict[str, Any], str]:
    """Return the final evidence manifest and one-time GO comment."""
    current_id = int(current_run["id"])
    current_started = _epoch(str(current_run["run_started_at"]))
    current_sha = str(current_run["head_sha"])
    if current_run.get("event") not in {"schedule", "workflow_dispatch"}:
        raise VerificationError("the current run has an invalid trigger")
    if current_run.get("head_branch") != "main":
        raise VerificationError("the current run is not on main")
    if current_started < end_epoch:
        raise VerificationError("the current observation precedes the +48h boundary")
    finalized_epoch = finalized_epoch or int(dt.datetime.now(dt.UTC).timestamp())
    if finalized_epoch < current_started:
        raise VerificationError("finalization time precedes the current observation")

    comments = _comments(comments_payload)
    private_clearance = _maintainer_comment(
        comments,
        PRIVATE_CLEAR_MARKER,
        not_before=max(end_epoch, finalized_epoch - 7200),
    )
    if private_clearance is None:
        raise VerificationError("the post-48h private-advisory clearance is missing")

    prior_runs = [
        run
        for run in _workflow_runs(runs_payload)
        if int(run["id"]) != current_id
        and run.get("event") in {"schedule", "workflow_dispatch"}
        and run.get("head_branch") == "main"
        and _epoch(str(run["run_started_at"])) >= start_epoch
    ]
    incomplete = [
        str(run["html_url"])
        for run in prior_runs
        if run.get("status") != "completed"
    ]
    if incomplete:
        raise VerificationError(f"prior observations are incomplete: {incomplete}")

    remote_runs = [*prior_runs, current_run]
    reruns = [
        str(run["html_url"])
        for run in remote_runs
        if int(run.get("run_attempt", 0)) != 1
    ]
    if reruns:
        raise VerificationError(
            f"rerun attempts cannot establish a fail-closed timeline: {reruns}"
        )
    monitor_shas = {str(run["head_sha"]) for run in remote_runs}
    if monitor_shas != {current_sha}:
        raise VerificationError(
            f"the monitor or default branch changed during the soak: {monitor_shas}"
        )

    incidents: list[dict[str, Any]] = []
    successful_runs: list[dict[str, Any]] = []
    for run in prior_runs:
        if run.get("conclusion") == "success":
            successful_runs.append(run)
            continue
        run_id = int(run["id"])
        marker = f"sdr-grader-v1.2.1-soak-run-{run_id}-triaged-infrastructure"
        disposition = _maintainer_comment(
            comments,
            marker,
            not_before=_epoch(str(run["updated_at"])),
        )
        if disposition is None:
            raise VerificationError(
                f"failed observation {run_id} has no maintainer infrastructure disposition"
            )
        incidents.append(
            {
                "run_id": run_id,
                "run_attempt": int(run["run_attempt"]),
                "run_url": str(run["html_url"]),
                "conclusion": str(run["conclusion"]),
                "disposition_url": str(disposition["html_url"]),
            }
        )

    observations = [
        {
            "kind": "local-start",
            "observed_at": _iso(start_epoch),
            "epoch": start_epoch,
            "url": start_url,
            "monitor_sha": None,
            "checkpoint_artifact": None,
        },
        *[
            {
                "kind": "github-actions",
                "observed_at": str(run["run_started_at"]),
                "epoch": _epoch(str(run["run_started_at"])),
                "url": str(run["html_url"]),
                "run_id": int(run["id"]),
                "run_attempt": int(run["run_attempt"]),
                "monitor_sha": str(run["head_sha"]),
                "checkpoint_artifact": (
                    f"sdr-grader-v1.2.1-soak-{int(run['id'])}"
                ),
            }
            for run in successful_runs
        ],
        {
            "kind": "github-actions-current",
            "observed_at": str(current_run["run_started_at"]),
            "epoch": current_started,
            "url": str(current_run["html_url"]),
            "run_id": current_id,
            "run_attempt": int(current_run["run_attempt"]),
            "monitor_sha": current_sha,
            "checkpoint_artifact": f"sdr-grader-v1.2.1-soak-{current_id}",
        },
    ]
    observations.sort(key=lambda item: (int(item["epoch"]), str(item["url"])))
    if len(observations) < 13:
        raise VerificationError(
            f"expected at least 13 successful observations, found {len(observations)}"
        )
    gaps = [
        int(right["epoch"]) - int(left["epoch"])
        for left, right in zip(observations[:-1], observations[1:], strict=True)
    ]
    if not gaps or max(gaps) > MAX_GAP_SECONDS:
        raise VerificationError(
            f"maximum successful-observation gap exceeds {MAX_GAP_SECONDS}: "
            f"{max(gaps, default=None)}"
        )

    checkpoints: dict[str, dict[str, Any]] = {}
    for hour in (4, 24, 48):
        target = start_epoch + hour * 3600
        checkpoint = next(
            (item for item in observations if int(item["epoch"]) >= target),
            None,
        )
        if checkpoint is None or int(checkpoint["epoch"]) - target > CHECKPOINT_TOLERANCE_SECONDS:
            raise VerificationError(f"+{hour}h checkpoint is missing or late")
        checkpoints[f"+{hour}h"] = {
            "target_at": _iso(target),
            "observed_at": checkpoint["observed_at"],
            "run_url": checkpoint["url"],
        }

    for left, right, gap in zip(
        observations[:-1],
        observations[1:],
        gaps,
        strict=True,
    ):
        right["gap_from_previous_seconds"] = gap
        right["previous_observation_url"] = left["url"]

    clearance_epoch = _epoch(str(private_clearance["created_at"]))
    if finalized_epoch < clearance_epoch:
        raise VerificationError("finalization time precedes private clearance")
    completed_at = _iso(finalized_epoch)
    manifest = {
        "schema_version": 1,
        "release": release,
        "release_commit": release_commit,
        "companion": companion,
        "monitor_sha": current_sha,
        "start_at": _iso(start_epoch),
        "end_boundary": _iso(end_epoch),
        "completed_at": completed_at,
        "maximum_gap_seconds": max(gaps),
        "observation_count": len(observations),
        "checkpoints": checkpoints,
        "observations": observations,
        "triaged_infrastructure_incidents": incidents,
        "private_advisory_clearance_url": str(private_clearance["html_url"]),
        "status": "PASS",
    }

    timeline_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    timeline_sha = hashlib.sha256(timeline_bytes).hexdigest()
    lines = [
        f"## {release} announcement GO",
        "",
        f"**GO — ready for public announcement at `{completed_at}`.**",
        "",
        f"The bounded 48-hour soak completed for exact release `{release}` / "
        f"`{release_commit}` with current companion `{companion}`.",
        "",
        f"- Start checkpoint: {start_url}",
    ]
    for hour in (4, 24, 48):
        checkpoint = checkpoints[f"+{hour}h"]
        lines.append(
            f"- +{hour}h checkpoint: {checkpoint['run_url']} "
            f"(`{checkpoint['observed_at']}`)"
        )
    lines.extend(
        [
            f"- Successful observations: {len(observations)}",
            f"- Maximum observation gap: {max(gaps)} seconds "
            f"(limit: {MAX_GAP_SECONDS})",
            f"- Frozen monitor/main revision: `{current_sha}`",
            f"- Post-48h private-report/security clearance: "
            f"{private_clearance['html_url']}",
            f"- Complete timeline manifest: attached to {current_run['html_url']} "
            f"with SHA-256 `{timeline_sha}`",
            "- Every successful checkpoint reverified exact public bytes/tags, "
            "provenance, clean Python 3.11/3.12 installs, AA/CJA fixture behavior, "
            "the remote Claude plugin, grader security alerts, and inbound issues",
            "- Current CJA and AA live flows passed from the public package at soak "
            "start; privacy-safe aggregate evidence is linked above",
            "- No additional broad repository audit was performed or required",
            "",
            "Brian Au is the release monitor, escalation contact, and announcement "
            "approver under the release authorization recorded in this PR.",
            "",
            f"<!-- {GO_MARKER} -->",
        ]
    )
    return manifest, "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--current-run", type=Path, required=True)
    parser.add_argument("--comments", type=Path, required=True)
    parser.add_argument("--timeline-output", type=Path, required=True)
    parser.add_argument("--comment-output", type=Path, required=True)
    parser.add_argument("--start-epoch", type=int, required=True)
    parser.add_argument("--end-epoch", type=int, required=True)
    parser.add_argument("--start-url", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--release-commit", required=True)
    parser.add_argument("--companion", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        manifest, comment = verify_timeline(
            runs_payload=json.loads(args.runs.read_text(encoding="utf-8")),
            current_run=json.loads(args.current_run.read_text(encoding="utf-8")),
            comments_payload=json.loads(args.comments.read_text(encoding="utf-8")),
            start_epoch=args.start_epoch,
            end_epoch=args.end_epoch,
            start_url=args.start_url,
            release=args.release,
            release_commit=args.release_commit,
            companion=args.companion,
        )
    except (KeyError, TypeError, ValueError, VerificationError) as exc:
        print(f"release soak timeline verification failed: {exc}")
        return 1
    timeline_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    args.timeline_output.write_bytes(timeline_bytes)
    args.comment_output.write_text(comment, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

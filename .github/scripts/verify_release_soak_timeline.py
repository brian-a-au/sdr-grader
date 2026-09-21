#!/usr/bin/env python3
"""Verify a release-soak timeline and emit its final evidence and completion comment."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

OWNER_LOGIN = "brian-a-au"
MAX_GAP_SECONDS = 14_400
CHECKPOINT_TOLERANCE_SECONDS = 7_200


class VerificationError(Exception):
    """The soak timeline does not support soak completion."""


class VerificationPending(VerificationError):
    """Healthy observations await elapsed time or fresh owner clearance."""


def _epoch(value: str) -> int:
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise VerificationError("malformed observation timestamp")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp())


def _iso(value: int) -> str:
    return dt.datetime.fromtimestamp(value, tz=dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _workflow_runs(payload: Any) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    runs: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
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
        if f"<!-- {marker} -->" in str(comment.get("body", "")).splitlines()
        and comment.get("author_association") == "OWNER"
        and comment.get("user", {}).get("login") == OWNER_LOGIN
        and _epoch(str(comment.get("created_at"))) >= not_before
    ]
    return sorted(matches, key=lambda item: str(item["created_at"]))[-1] if matches else None


def completed_jobs(payload, run_id, finalized_epoch):
    pages = payload if isinstance(payload, list) else [payload]
    jobs = [job for page in pages for job in page.get("jobs", [])]
    times = []
    for name in (
        "Public release checkpoint",
        "Grader security and inbound reports",
        "Retain aggregate checkpoint",
    ):
        matches = [job for job in jobs if job.get("name") == name]
        if len(matches) != 1:
            raise VerificationError("required jobs missing or duplicate")
        job = matches[0]
        if (
            job.get("run_id") != run_id
            or job.get("run_attempt") != 1
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
        ):
            raise VerificationError("required jobs are not successful first-attempt jobs")
        completed = _epoch(job["completed_at"])
        if completed > finalized_epoch:
            raise VerificationError("jobs completion is in the future")
        times.append(completed)
    return max(times)


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
    companion: Any,
    marker_prefix: str,
    finalized_epoch: int | None = None,
    current_jobs: Any = None,
    start_jobs: Any = None,
    start_run: Any = None,
    start_proof: Any = None,
    config_sha: str = "",
    monitor_commit: str = "",
    allow_pending: bool = False,
) -> tuple[dict[str, Any], str]:
    """Return the final evidence manifest and one-time completion comment."""
    finalized_epoch = finalized_epoch or int(dt.datetime.now(dt.UTC).timestamp())
    if end_epoch - start_epoch < 172800:
        raise VerificationError("window must be at least 48 hours")
    if current_jobs is None or start_jobs is None:
        raise VerificationError("required jobs evidence missing")
    actual_start = completed_jobs(start_jobs, int(start_run["id"]), finalized_epoch)
    actual_current = completed_jobs(current_jobs, int(current_run["id"]), finalized_epoch)
    if not start_epoch <= actual_start <= start_epoch + CHECKPOINT_TOLERANCE_SECONDS:
        raise VerificationError("start checkpoint outside start tolerance")
    if (
        start_proof.get("html_url") != start_url
        or start_proof.get("author_association") != "OWNER"
        or start_proof.get("user", {}).get("login") != OWNER_LOGIN
    ):
        raise VerificationError("start proof is not the configured owner comment")
    expected_proof = {
        "config_sha256": config_sha,
        "release_commit": release_commit,
        "head_sha": current_run["head_sha"],
        "run_id": start_run["id"],
        "window": marker_prefix,
    }
    if json.loads(start_proof["body"]) != expected_proof:
        raise VerificationError("start proof identities differ")
    if start_run.get("status") != "completed" or start_run.get("conclusion") != "success":
        raise VerificationError("start run did not complete successfully")
    current_id = int(current_run["id"])
    current_started = _epoch(str(current_run["run_started_at"]))
    current_sha = str(current_run["head_sha"])
    if current_run.get("event") not in {"schedule", "workflow_dispatch"}:
        raise VerificationError("the current run has an invalid trigger")
    if current_run.get("head_branch") != "main":
        raise VerificationError("the current run is not on main")
    if finalized_epoch < current_started:
        raise VerificationError("finalization time precedes the current observation")

    comments = _comments(comments_payload)
    private_clearance = _maintainer_comment(
        comments,
        f"{marker_prefix}-private-advisory-clear",
        not_before=max(end_epoch, actual_start + 172800, finalized_epoch - 7200),
    )
    if (
        private_clearance is not None
        and _epoch(str(private_clearance["created_at"])) > finalized_epoch
    ):
        raise VerificationError("finalization time precedes private clearance")

    all_runs = _workflow_runs(runs_payload)
    for run in all_runs:
        started = _epoch(str(run["run_started_at"]))
        if started >= start_epoch and (
            run.get("event") not in {"schedule", "workflow_dispatch"}
            or run.get("head_branch") != "main"
        ):
            raise VerificationError("foreign trigger or branch during window")
    prior_runs = [
        run
        for run in all_runs
        if int(run["id"]) != current_id
        and run.get("event") in {"schedule", "workflow_dispatch"}
        and run.get("head_branch") == "main"
        and _epoch(str(run["run_started_at"])) >= start_epoch
    ]
    if len({run["id"] for run in all_runs}) != len(all_runs):
        raise VerificationError("duplicate run identities")
    if not any(run == start_run for run in prior_runs):
        raise VerificationError("start run missing from timeline")
    for run in [*prior_runs, current_run]:
        if (
            run.get("path") != ".github/workflows/release-soak.yml"
            or run.get("repository", {}).get("full_name") != "brian-a-au/sdr-grader"
        ):
            raise VerificationError("foreign workflow observation")
        if run["html_url"] != f"https://github.com/brian-a-au/sdr-grader/actions/runs/{run['id']}":
            raise VerificationError("foreign observation URL")
        if (
            _epoch(run["updated_at"]) > finalized_epoch
            or _epoch(run["run_started_at"]) > finalized_epoch
        ):
            raise VerificationError("future observation")
    incomplete = [str(run["html_url"]) for run in prior_runs if run.get("status") != "completed"]
    if incomplete:
        raise VerificationError(f"prior observations are incomplete: {incomplete}")

    remote_runs = [*prior_runs, current_run]
    reruns = [str(run["html_url"]) for run in remote_runs if int(run.get("run_attempt", 0)) != 1]
    if reruns:
        raise VerificationError(f"rerun attempts cannot establish a fail-closed timeline: {reruns}")
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
        marker = f"{marker_prefix}-soak-run-{run_id}-triaged-infrastructure"
        disposition = _maintainer_comment(
            comments,
            marker,
            not_before=_epoch(str(run["updated_at"])),
        )
        if disposition is None:
            raise VerificationError(
                f"failed observation {run_id} has no maintainer infrastructure disposition"
            )
        if _epoch(str(disposition["created_at"])) > finalized_epoch:
            raise VerificationError("future infrastructure disposition")
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
        *[
            {
                "kind": "github-actions",
                "observed_at": _iso(actual_start)
                if run["id"] == start_run["id"]
                else str(run["updated_at"]),
                "epoch": actual_start
                if run["id"] == start_run["id"]
                else _epoch(str(run["updated_at"])),
                "url": str(run["html_url"]),
                "run_id": int(run["id"]),
                "run_attempt": int(run["run_attempt"]),
                "monitor_sha": str(run["head_sha"]),
                "checkpoint_artifact": f"{marker_prefix}-soak-{int(run['id'])}",
            }
            for run in successful_runs
        ],
        {
            "kind": "github-actions-current",
            "observed_at": _iso(actual_current),
            "epoch": actual_current,
            "url": str(current_run["html_url"]),
            "run_id": current_id,
            "run_attempt": int(current_run["run_attempt"]),
            "monitor_sha": current_sha,
            "checkpoint_artifact": f"{marker_prefix}-soak-{current_id}",
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

    waiting_error = VerificationPending if allow_pending else VerificationError
    if actual_current < max(end_epoch, actual_start + 172800):
        raise waiting_error("less than 48 hours since proven start or configured boundary pending")

    checkpoints: dict[str, dict[str, Any]] = {}
    for hour in (4, 24, 48):
        target = actual_start + hour * 3600
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

    if private_clearance is None:
        raise waiting_error("the post-48h private-advisory clearance is missing or stale")
    clearance_epoch = _epoch(str(private_clearance["created_at"]))
    if finalized_epoch < clearance_epoch:
        raise VerificationError("finalization time precedes private clearance")
    completed_at = _iso(finalized_epoch)
    manifest = {
        "schema_version": 1,
        "release": release,
        "release_commit": release_commit,
        "companion": companion,
        "marker_prefix": marker_prefix,
        "monitor_sha": current_sha,
        "start_at": _iso(actual_start),
        "config_sha256": config_sha,
        "monitor_implementation_commit": monitor_commit,
        "start_evidence_url": start_url,
        "start_run_url": start_run["html_url"],
        "end_boundary": _iso(end_epoch),
        "completed_at": completed_at,
        "maximum_gap_seconds": max(gaps),
        "observation_count": len(observations),
        "checkpoints": checkpoints,
        "observations": observations,
        "triaged_infrastructure_incidents": incidents,
        "private_advisory_clearance_url": str(private_clearance["html_url"]),
        "status": "SOAK_COMPLETE",
    }

    timeline_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    timeline_sha = hashlib.sha256(timeline_bytes).hexdigest()
    comment = (
        f"## {release} soak complete\n\n"
        f"SOAK_COMPLETE at `{completed_at}`. Announcement approval, final audit, "
        "and live-flow evidence remain separate release gates.\n\n"
        f"Timeline SHA-256: `{timeline_sha}`\n\n"
        f"<!-- {marker_prefix}-soak-complete -->\n\n"
        "```json\n" + timeline_bytes.decode() + "```\n"
    )
    if len(comment) > 60000:
        raise VerificationError("durable timeline exceeds comment size limit")
    return manifest, comment


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--current-run", type=Path, required=True)
    parser.add_argument("--comments", type=Path, required=True)
    parser.add_argument("--timeline-output", type=Path, required=True)
    parser.add_argument("--comment-output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--readiness-output", type=Path)
    for name in ("current-jobs", "start-jobs", "start-run", "start-proof"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        from validate_release_soak_config import epoch, validate

        config_bytes = args.config.read_bytes()
        config = json.loads(config_bytes)
        env = validate(config)
        if not config["active"]:
            raise VerificationError("inactive candidate")
        manifest, comment = verify_timeline(
            runs_payload=json.loads(args.runs.read_bytes()),
            current_run=json.loads(args.current_run.read_bytes()),
            comments_payload=json.loads(args.comments.read_bytes()),
            current_jobs=json.loads(args.current_jobs.read_bytes()),
            start_jobs=json.loads(args.start_jobs.read_bytes()),
            start_run=json.loads(args.start_run.read_bytes()),
            start_proof=json.loads(args.start_proof.read_bytes()),
            start_epoch=epoch(config["start_at"]),
            end_epoch=epoch(config["end_at"]),
            start_url=config["start_evidence_url"],
            release=f"sdr-grader v{config['release']['version']}",
            release_commit=config["release"]["commit"],
            companion=config["companion"],
            marker_prefix=env["SOAK_MARKER_PREFIX"],
            config_sha=hashlib.sha256(config_bytes).hexdigest(),
            monitor_commit=config["monitor_commit"],
            allow_pending=args.readiness_output is not None,
        )
    except VerificationPending as exc:
        print(f"release soak pending: {exc}")
        with args.readiness_output.open("a") as output:
            output.write("ready=false\n")
        return 0
    except (KeyError, TypeError, ValueError, VerificationError) as exc:
        print(f"release soak timeline verification failed: {exc}")
        return 1
    timeline_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    args.timeline_output.write_bytes(timeline_bytes)
    args.comment_output.write_text(comment, encoding="utf-8")
    if args.readiness_output is not None:
        with args.readiness_output.open("a") as output:
            output.write("ready=true\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

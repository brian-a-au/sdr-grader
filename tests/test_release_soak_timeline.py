from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / ".github/scripts/verify_release_soak_timeline.py"
spec = importlib.util.spec_from_file_location("timeline", SCRIPT)
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)
START = 1800000000
END = START + 48 * 3600
SHA = "a" * 40
PREFIX = "sdr-grader-v7.8.9-window-1234"


def run(hour, conclusion="success"):
    return dict(
        id=1000 + hour,
        event="schedule",
        head_branch="main",
        head_sha=SHA,
        path=".github/workflows/release-soak.yml",
        repository={"full_name": "brian-a-au/sdr-grader"},
        run_started_at=MODULE._iso(START + hour * 3600 - 60),
        updated_at=MODULE._iso(START + hour * 3600),
        status="completed" if conclusion else "in_progress",
        conclusion=conclusion,
        html_url=f"https://github.com/brian-a-au/sdr-grader/actions/runs/{1000 + hour}",
        run_attempt=1,
    )


def jobs(hour):
    return {
        "jobs": [
            dict(
                name=name,
                run_id=1000 + hour,
                run_attempt=1,
                status="completed",
                conclusion="success",
                completed_at=MODULE._iso(START + hour * 3600),
            )
            for name in (
                "Public release checkpoint",
                "Grader security and inbound reports",
                "Retain aggregate checkpoint",
            )
        ]
    }


def inputs():
    start = run(0)
    # Start run begins at the configured boundary and completes one minute later.
    start["run_started_at"] = MODULE._iso(START)
    return dict(
        runs_payload={"workflow_runs": [start, *[run(i) for i in range(1, 48)]]},
        current_run=run(48, None),
        comments_payload=[
            dict(
                body=f"<!-- {PREFIX}-private-advisory-clear -->",
                author_association="OWNER",
                user={"login": "brian-a-au"},
                created_at=MODULE._iso(END + 60),
                html_url="https://example.test/clearance",
            )
        ],
        start_epoch=START,
        end_epoch=END,
        start_url="https://example.test/start",
        release="sdr-grader v7.8.9",
        release_commit="b" * 40,
        companion={"applicable": False, "reason": "grader only"},
        marker_prefix=PREFIX,
        finalized_epoch=END + 120,
        current_jobs=jobs(48),
        start_jobs=jobs(0),
        start_run=start,
        config_sha="c" * 64,
        monitor_commit="d" * 40,
        start_proof=dict(
            html_url="https://example.test/start",
            author_association="OWNER",
            user={"login": "brian-a-au"},
            body=json.dumps(
                dict(
                    config_sha256="c" * 64,
                    release_commit="b" * 40,
                    head_sha=SHA,
                    run_id=1000,
                    window=PREFIX,
                )
            ),
        ),
    )


def test_frozen_success_retains_complete_truthful_evidence():
    manifest, comment = MODULE.verify_timeline(**inputs())
    assert manifest["status"] == "SOAK_COMPLETE"
    assert manifest["observation_count"] == 49
    assert manifest["maximum_gap_seconds"] == 3600
    assert "announcement GO" not in comment
    assert "live flows passed" not in comment
    assert "```json" in comment
    assert set(manifest["checkpoints"]) == {"+4h", "+24h", "+48h"}


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_jobs",
        "failed_jobs",
        "duplicate_jobs",
        "wrong_attempt",
        "skipped_jobs",
        "short_window",
        "late_start",
        "false_proof",
        "foreign",
        "future",
        "rerun",
        "moved",
        "untriaged",
        "gap",
        "stale",
        "nonowner",
        "marker_suffix",
        "malformed",
    ],
)
def test_rejects_unproven_or_unhealthy_timeline(mutation):
    data = inputs()
    runs = data["runs_payload"]["workflow_runs"]
    if mutation == "missing_jobs":
        data["current_jobs"] = None
    if mutation == "failed_jobs":
        data["current_jobs"]["jobs"][0]["conclusion"] = "failure"
    if mutation == "duplicate_jobs":
        data["current_jobs"]["jobs"].append(data["current_jobs"]["jobs"][0])
    if mutation == "wrong_attempt":
        data["current_jobs"]["jobs"][0]["run_attempt"] = 2
    if mutation == "skipped_jobs":
        data["current_jobs"]["jobs"][0]["conclusion"] = "skipped"
    if mutation == "short_window":
        data["end_epoch"] -= 1
    if mutation == "late_start":
        data["start_jobs"]["jobs"][0]["completed_at"] = MODULE._iso(START + 300)
    if mutation == "false_proof":
        data["start_proof"]["body"] = "{}"
    if mutation == "foreign":
        runs[10]["repository"]["full_name"] = "other/repo"
    if mutation == "future":
        runs[10]["updated_at"] = MODULE._iso(END + 500)
    if mutation == "rerun":
        runs[10]["run_attempt"] = 2
    if mutation == "moved":
        runs[10]["head_sha"] = "f" * 40
    if mutation == "untriaged":
        runs[10]["conclusion"] = "failure"
    if mutation == "gap":
        del runs[1:6]
    if mutation == "stale":
        data["comments_payload"][0]["created_at"] = MODULE._iso(END - 1)
    if mutation == "nonowner":
        data["comments_payload"][0]["author_association"] = "COLLABORATOR"
    if mutation == "marker_suffix":
        data["comments_payload"][0]["body"] += "-forged"
    if mutation == "malformed":
        runs[10]["run_started_at"] = "2026-01-01"
    with pytest.raises(MODULE.VerificationError):
        MODULE.verify_timeline(**data)


def test_infrastructure_disposition_is_not_an_observation():
    data = inputs()
    data["runs_payload"]["workflow_runs"][12]["conclusion"] = "failure"
    data["comments_payload"].append(
        dict(
            body=f"<!-- {PREFIX}-soak-run-1012-triaged-infrastructure -->",
            user={"login": "brian-a-au"},
            author_association="OWNER",
            created_at=MODULE._iso(START + 13 * 3600),
            html_url="https://example.test/disposition",
        )
    )
    manifest, _ = MODULE.verify_timeline(**data)
    assert manifest["observation_count"] == 48
    assert manifest["maximum_gap_seconds"] == 7200


@pytest.mark.parametrize("reason", ["elapsed", "clearance", "stale_clearance"])
def test_expected_pending_is_not_a_failed_observation(reason):
    data = inputs()
    data["allow_pending"] = True
    if reason == "elapsed":
        data["start_jobs"]["jobs"][0]["completed_at"] = MODULE._iso(START + 300)
    elif reason == "clearance":
        data["comments_payload"] = []
    else:
        data["comments_payload"][0]["created_at"] = MODULE._iso(END - 1)
    with pytest.raises(MODULE.VerificationPending):
        MODULE.verify_timeline(**data)


def test_pending_clearance_cannot_mask_foreign_observation():
    data = inputs()
    data["allow_pending"] = True
    data["comments_payload"] = []
    data["runs_payload"]["workflow_runs"][10]["head_sha"] = "f" * 40
    with pytest.raises(MODULE.VerificationError, match="changed during"):
        MODULE.verify_timeline(**data)


def test_pending_cli_does_not_write_completion_evidence(tmp_path, monkeypatch):
    import argparse
    import sys
    import types

    payload = tmp_path / "input.json"
    payload.write_text(
        json.dumps(
            {
                "active": True,
                "start_at": "unused",
                "end_at": "unused",
                "start_evidence_url": "unused",
                "release": {"version": "7.8.9", "commit": "b" * 40},
                "companion": {},
                "monitor_commit": "d" * 40,
            }
        )
    )
    args = argparse.Namespace(
        **{
            name: payload
            for name in (
                "config",
                "runs",
                "current_run",
                "comments",
                "current_jobs",
                "start_jobs",
                "start_run",
                "start_proof",
            )
        },
        readiness_output=tmp_path / "output",
        timeline_output=tmp_path / "timeline.json",
        comment_output=tmp_path / "comment.md",
    )
    monkeypatch.setattr(MODULE, "_parse_args", lambda: args)
    monkeypatch.setitem(
        sys.modules,
        "validate_release_soak_config",
        types.SimpleNamespace(
            epoch=lambda _: START, validate=lambda _: {"SOAK_MARKER_PREFIX": PREFIX}
        ),
    )

    def pending(**kwargs):
        assert kwargs["allow_pending"] is True
        raise MODULE.VerificationPending("awaiting fresh clearance")

    monkeypatch.setattr(MODULE, "verify_timeline", pending)
    assert MODULE.main() == 0
    assert args.readiness_output.read_text() == "ready=false\n"
    assert not args.timeline_output.exists()
    assert not args.comment_output.exists()

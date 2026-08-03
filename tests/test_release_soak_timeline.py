from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / ".github" / "scripts" / "verify_release_soak_timeline.py"
START = 1_785_646_474
END = START + 48 * 3600
MONITOR_SHA = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_release_soak_timeline",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _iso(epoch: int) -> str:
    return MODULE._iso(epoch)


def _run(hour: int, *, conclusion: str | None = "success", sha: str = MONITOR_SHA):
    run_id = 10_000 + hour
    started = START + hour * 3600
    return {
        "id": run_id,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": sha,
        "run_started_at": _iso(started),
        "updated_at": _iso(started + 300),
        "status": "completed" if conclusion is not None else "in_progress",
        "conclusion": conclusion,
        "html_url": f"https://example.test/runs/{run_id}",
        "run_attempt": 1,
    }


def _private_clearance(marker_prefix: str = "sdr-grader-v1.2.2"):
    return {
        "body": f"<!-- {marker_prefix}-private-advisory-clear -->",
        "author_association": "OWNER",
        "user": {"login": "brian-a-au"},
        "created_at": _iso(END + 60),
        "html_url": "https://example.test/private-clearance",
    }


def _verify(runs, current=None, comments=None, *, marker_prefix="sdr-grader-v1.2.2"):
    return MODULE.verify_timeline(
        runs_payload={"workflow_runs": runs},
        current_run=current or _run(48, conclusion=None),
        comments_payload=(
            comments
            if comments is not None
            else [_private_clearance(marker_prefix)]
        ),
        start_epoch=START,
        end_epoch=END,
        start_url="https://example.test/start",
        release="sdr-grader v1.2.2",
        release_commit="b" * 40,
        companion="sdr-visualizer v1.0.6",
        marker_prefix=marker_prefix,
        finalized_epoch=END + 120,
    )


def test_timeline_accepts_frozen_hourly_successes_and_emits_full_evidence():
    runs = [_run(hour) for hour in range(1, 48)]

    manifest, comment = _verify(runs)

    assert manifest["status"] == "PASS"
    assert manifest["marker_prefix"] == "sdr-grader-v1.2.2"
    assert manifest["monitor_sha"] == MONITOR_SHA
    assert manifest["observation_count"] == 49
    assert manifest["maximum_gap_seconds"] == 3600
    assert manifest["completed_at"] == _iso(END + 120)
    assert set(manifest["checkpoints"]) == {"+4h", "+24h", "+48h"}
    assert len(manifest["observations"]) == 49
    assert manifest["private_advisory_clearance_url"].endswith(
        "private-clearance"
    )
    assert "announcement GO" in comment
    assert "sdr-grader-v1.2.2-announcement-go" in comment


def test_timeline_derives_all_markers_from_an_arbitrary_prefix():
    prefix = "custom-soak-marker"
    runs = [_run(hour) for hour in range(1, 48)]
    failed = _run(12, conclusion="failure")
    runs[11] = failed
    disposition = {
        "body": f"<!-- {prefix}-soak-run-10012-triaged-infrastructure -->",
        "author_association": "OWNER",
        "user": {"login": "brian-a-au"},
        "created_at": _iso(START + 12 * 3600 + 600),
        "html_url": "https://example.test/infrastructure-triage",
    }

    manifest, comment = _verify(
        runs,
        comments=[_private_clearance(prefix), disposition],
        marker_prefix=prefix,
    )

    assert manifest["marker_prefix"] == prefix
    assert manifest["observations"][1]["checkpoint_artifact"].startswith(prefix)
    assert manifest["triaged_infrastructure_incidents"][0]["run_id"] == 10012
    assert f"{prefix}-announcement-go" in comment


def test_timeline_rejects_gap_over_four_hours():
    runs = [_run(hour) for hour in range(1, 48) if hour not in {2, 3, 4, 5}]

    with pytest.raises(MODULE.VerificationError, match="gap exceeds"):
        _verify(runs)


def test_timeline_rejects_monitor_or_main_revision_movement():
    runs = [_run(hour) for hour in range(1, 48)]
    runs[12] = _run(13, sha="c" * 40)

    with pytest.raises(MODULE.VerificationError, match="changed during the soak"):
        _verify(runs)


def test_timeline_rejects_non_main_manual_finalization():
    runs = [_run(hour) for hour in range(1, 48)]
    current = _run(48, conclusion=None)
    current["event"] = "workflow_dispatch"
    current["head_branch"] = "feature/untrusted-finalization"

    with pytest.raises(MODULE.VerificationError, match="not on main"):
        _verify(runs, current=current)


def test_timeline_rejects_untriaged_failed_observation():
    runs = [_run(hour) for hour in range(1, 48)]
    runs[11] = _run(12, conclusion="failure")

    with pytest.raises(MODULE.VerificationError, match="no maintainer"):
        _verify(runs)


def test_timeline_rejects_a_successful_rerun_that_hides_an_earlier_attempt():
    runs = [_run(hour) for hour in range(1, 48)]
    runs[11]["run_attempt"] = 2

    with pytest.raises(MODULE.VerificationError, match="rerun attempts"):
        _verify(runs)


def test_timeline_accepts_owner_triaged_infrastructure_failure():
    runs = [_run(hour) for hour in range(1, 48)]
    failed = _run(12, conclusion="failure")
    runs[11] = failed
    disposition = {
        "body": (
            "Transient GitHub runner outage; release checks passed on retry.\n"
            "<!-- sdr-grader-v1.2.2-soak-run-10012-triaged-infrastructure -->"
        ),
        "author_association": "OWNER",
        "user": {"login": "brian-a-au"},
        "created_at": _iso(START + 12 * 3600 + 600),
        "html_url": "https://example.test/infrastructure-triage",
    }

    manifest, _comment = _verify(
        runs,
        comments=[_private_clearance(), disposition],
    )

    assert manifest["maximum_gap_seconds"] == 7200
    assert manifest["triaged_infrastructure_incidents"] == [
        {
            "run_id": 10012,
            "run_attempt": 1,
            "run_url": failed["html_url"],
            "conclusion": "failure",
            "disposition_url": disposition["html_url"],
        }
    ]


def test_timeline_requires_post_boundary_private_advisory_clearance():
    runs = [_run(hour) for hour in range(1, 48)]

    with pytest.raises(MODULE.VerificationError, match="private-advisory"):
        _verify(runs, comments=[])


def test_timeline_rejects_stale_or_non_owner_private_clearance():
    runs = [_run(hour) for hour in range(1, 48)]
    stale = _private_clearance()
    stale["created_at"] = _iso(END + 60)
    collaborator = _private_clearance()
    collaborator["created_at"] = _iso(END + 10_900)
    collaborator["author_association"] = "COLLABORATOR"
    collaborator["user"] = {"login": "someone-else"}

    with pytest.raises(MODULE.VerificationError, match="private-advisory"):
        MODULE.verify_timeline(
            runs_payload={"workflow_runs": runs},
            current_run=_run(51, conclusion=None),
            comments_payload=[stale, collaborator],
            start_epoch=START,
            end_epoch=END,
            start_url="https://example.test/start",
            release="sdr-grader v1.2.2",
            release_commit="b" * 40,
            companion="sdr-visualizer v1.0.6",
            marker_prefix="sdr-grader-v1.2.2",
            finalized_epoch=END + 11_000,
        )


def test_timeline_never_backdates_go_before_private_clearance():
    runs = [_run(hour) for hour in range(1, 48)]
    clearance = _private_clearance()
    clearance["created_at"] = _iso(END + 180)

    with pytest.raises(MODULE.VerificationError, match="precedes private clearance"):
        MODULE.verify_timeline(
            runs_payload={"workflow_runs": runs},
            current_run=_run(48, conclusion=None),
            comments_payload=[clearance],
            start_epoch=START,
            end_epoch=END,
            start_url="https://example.test/start",
            release="sdr-grader v1.2.2",
            release_commit="b" * 40,
            companion="sdr-visualizer v1.0.6",
            marker_prefix="sdr-grader-v1.2.2",
            finalized_epoch=END + 120,
        )

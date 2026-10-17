"""Exercise the external release-soak driver with synthetic run histories."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "release_soak_driver",
    Path(__file__).parents[1] / "scripts" / "release_soak_driver.py",
)
assert _spec is not None
assert _spec.loader is not None
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def iso(delta: timedelta) -> str:
    return (NOW - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(
    age: timedelta,
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    branch: str = "main",
    updated: timedelta | None = None,
) -> dict[str, str]:
    return {
        "databaseId": "1",
        "status": status,
        "conclusion": conclusion or "",
        "createdAt": iso(age),
        "updatedAt": iso(updated if updated is not None else age),
        "event": "schedule",
        "headBranch": branch,
    }


def test_decide_dispatches_when_no_runs():
    assert driver.decide([], NOW).dispatch is True


def test_decide_never_dispatches_while_a_run_is_pending():
    d = driver.decide([run(timedelta(hours=2), status="queued", conclusion=None)], NOW)
    assert d.dispatch is False


def test_decide_respects_interval():
    assert driver.decide([run(timedelta(minutes=10))], NOW).dispatch is False
    assert driver.decide([run(timedelta(minutes=31))], NOW).dispatch is True


def test_decide_alerts_after_three_hours_without_success():
    d = driver.decide([run(timedelta(hours=3, minutes=1))], NOW)
    assert d.alert is not None
    assert "no successful observation" in d.alert
    assert "181 minutes" in d.alert


def test_decide_ignores_non_main_runs():
    runs = [
        run(timedelta(minutes=1), branch="feature", status="queued", conclusion=None),
        run(timedelta(minutes=1), branch="feature"),
    ]
    d = driver.decide(runs, NOW)
    assert d.dispatch is True
    assert d.alert == "no successful observation in listed history"


@pytest.fixture
def calls() -> list[list[str]]:
    return []


def fake_run_factory(runs, calls, fail_dispatch=False):
    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if fail_dispatch and cmd[:3] == ["gh", "workflow", "run"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="x")
        out = json.dumps(runs) if cmd[:3] == ["gh", "run", "list"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    return fake_run


def test_main_invokes_gh_with_exact_arguments(monkeypatch, calls):
    monkeypatch.setattr(driver.subprocess, "run", fake_run_factory([], calls))
    driver.main([])
    assert calls[0] == [
        "gh", "run", "list", "--workflow", "release-soak.yml", "--branch", "main",
        "--limit", "20", "--json",
        "databaseId,status,conclusion,createdAt,updatedAt,event,headBranch",
    ]  # fmt: skip
    assert ["gh", "workflow", "run", "release-soak.yml", "--ref", "main"] in calls
    assert not any(c[:3] == ["gh", "run", "rerun"] for c in calls)


def test_dry_run_never_dispatches(monkeypatch, capsys, calls):
    monkeypatch.setattr(driver.subprocess, "run", fake_run_factory([], calls))
    driver.main(["--dry-run"])
    assert not any(c[:3] == ["gh", "workflow", "run"] for c in calls)
    assert "dispatch=True" in capsys.readouterr().out


def test_gh_failure_returns_one(monkeypatch, capsys, calls):
    def boom(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="x")

    monkeypatch.setattr(driver.subprocess, "run", boom)
    assert driver.main([]) == 1
    assert capsys.readouterr().err


def test_unknown_unfinished_status_blocks_dispatch():
    d = driver.decide([run(timedelta(hours=2), status="action_required", conclusion=None)], NOW)
    assert d.dispatch is False


def test_success_requires_observation_event():
    other = run(timedelta(minutes=5))
    other["event"] = "push"
    assert driver.decide([other], NOW).alert == "no successful observation in listed history"


def test_naive_timestamps_do_not_crash():
    r = run(timedelta(minutes=5))
    r["createdAt"] = r["updatedAt"] = "2026-10-17T11:55:00"
    assert driver.decide([r], NOW).dispatch is False


def test_main_returns_two_on_alert(monkeypatch, calls):
    monkeypatch.setattr(driver.subprocess, "run", fake_run_factory([], calls))
    assert driver.main(["--dry-run"]) == 2


def test_dispatch_failure_returns_one(monkeypatch, capsys, calls):
    monkeypatch.setattr(driver.subprocess, "run", fake_run_factory([], calls, True))
    assert driver.main([]) == 1
    assert "could not dispatch with gh" in capsys.readouterr().err

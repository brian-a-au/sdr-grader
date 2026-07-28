"""Portable output naming, collision checks, and staged publication."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from sdr_grader.cli import output as output_module
from sdr_grader.cli.main import _default_output_path, _default_trend_output_path
from sdr_grader.cli.output import (
    MAX_DERIVED_LEAF_BYTES,
    OutputPathError,
    OutputPublishError,
    portable_leaf,
    publish_text_artifacts,
    validate_output_paths,
)


@pytest.mark.parametrize(
    "identity",
    [
        "../escape",
        r"..\escape",
        "/tmp/escape",
        r"C:\escape",
        r"\\server\share",
        "..",
        "tenant／escape",
        "\ud800",
        "x" * 500,
        "CON",
        "NUL.txt",
    ],
)
def test_portable_leaf_contains_hostile_cross_platform_tokens(identity):
    leaf = portable_leaf("grade-", identity, ".html")

    assert leaf == Path(leaf).name
    assert leaf not in {".", ".."}
    assert "/" not in leaf
    assert "\\" not in leaf
    assert leaf.isascii()
    assert len(leaf.encode("ascii")) <= MAX_DERIVED_LEAF_BYTES


def test_default_normal_and_trend_paths_are_single_bounded_leaves():
    report_path = _default_output_path(SimpleNamespace(id="../" + "x" * 500))
    trend = SimpleNamespace(
        instance_id=r"C:\tenant\..\escape",
        latest=SimpleNamespace(timestamp=datetime(2026, 7, 28, tzinfo=UTC)),
    )
    trend_path = _default_trend_output_path(trend)

    for path in (report_path, trend_path):
        assert path.parent == Path(".")
        assert len(path.name.encode("ascii")) <= MAX_DERIVED_LEAF_BYTES


def test_portable_leaf_rejects_impossible_budget():
    with pytest.raises(ValueError, match="budget"):
        portable_leaf("grade-", "instance", ".html", max_bytes=20)


def test_validate_output_paths_rejects_output_and_input_aliases(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")

    with pytest.raises(OutputPathError, match="collides with an input"):
        validate_output_paths(
            [tmp_path / "." / "snapshot.json"],
            read_paths=[snapshot],
        )


def test_validate_output_paths_resolves_symlinked_input_alias(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")
    snapshot_link = tmp_path / "snapshot-link.json"
    snapshot_link.symlink_to(snapshot)

    with pytest.raises(OutputPathError, match="collides with an input"):
        validate_output_paths([snapshot], read_paths=[snapshot_link])


def test_validate_output_paths_rejects_duplicate_destinations(tmp_path):
    with pytest.raises(OutputPathError, match="same file"):
        validate_output_paths(
            [tmp_path / "report.html", tmp_path / "." / "report.html"]
        )


def test_validate_output_paths_rejects_symlink_and_nonregular_targets(tmp_path):
    target = tmp_path / "target.html"
    target.write_text("old", encoding="utf-8")
    symlink = tmp_path / "link.html"
    symlink.symlink_to(target)

    with pytest.raises(OutputPathError, match="symlink"):
        validate_output_paths([symlink])
    with pytest.raises(OutputPathError, match="regular file"):
        validate_output_paths([tmp_path])


def test_staging_failure_preserves_every_final_and_cleans_stages(tmp_path, monkeypatch):
    html = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    html.write_text("old html", encoding="utf-8")
    json_path.write_text("old json", encoding="utf-8")
    real_write_stage = output_module._write_stage
    calls = 0

    def fail_second_stage(stage, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        real_write_stage(stage, content)

    monkeypatch.setattr(output_module, "_write_stage", fail_second_stage)

    with pytest.raises(OutputPublishError, match="stage"):
        publish_text_artifacts({html: "new html", json_path: "new json"})

    assert html.read_text(encoding="utf-8") == "old html"
    assert json_path.read_text(encoding="utf-8") == "old json"
    assert list(tmp_path.glob(".sdr-grader-*.stage")) == []


def test_commit_failure_reports_no_success_and_cleans_unpublished_stage(
    tmp_path,
    monkeypatch,
):
    html = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    html.write_text("old html", encoding="utf-8")
    json_path.write_text("old json", encoding="utf-8")
    real_replace = output_module.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(output_module.os, "replace", fail_second_replace)

    with pytest.raises(OutputPublishError, match="no success"):
        publish_text_artifacts({html: "new html", json_path: "new json"})

    # Cross-file transactionality is intentionally not claimed once commit starts.
    assert html.read_text(encoding="utf-8") == "new html"
    assert json_path.read_text(encoding="utf-8") == "old json"
    assert list(tmp_path.glob(".sdr-grader-*.stage")) == []


@pytest.mark.parametrize("stage_kind", ["symlink", "directory"])
def test_unsafe_stale_stage_fails_closed(tmp_path, stage_kind):
    destination = tmp_path / "report.html"
    stage = output_module._stage_path(destination)
    if stage_kind == "symlink":
        target = tmp_path / "attacker.txt"
        target.write_text("attacker", encoding="utf-8")
        stage.symlink_to(target)
    else:
        stage.mkdir()

    with pytest.raises(OutputPublishError, match="stage"):
        publish_text_artifacts({destination: "complete"})

    assert not destination.exists()


def test_stage_write_failure_removes_incomplete_stage(tmp_path, monkeypatch):
    stage = tmp_path / ".report.stage"

    def fail_fsync(_descriptor):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(output_module.os, "fsync", fail_fsync)

    with pytest.raises(OSError):
        output_module._write_stage(stage, "incomplete")

    assert not stage.exists()


def test_next_run_cleans_owned_stale_stage(tmp_path):
    destination = tmp_path / "report.html"
    stage = output_module._stage_path(destination)
    stage.write_text("interrupted", encoding="utf-8")

    publish_text_artifacts({destination: "complete"})

    assert destination.read_text(encoding="utf-8") == "complete"
    assert not stage.exists()
    assert os.stat(destination).st_mode & 0o077 == 0

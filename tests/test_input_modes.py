"""Tests for input/loader.py and CLI input-mode dispatch."""

from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sdr_grader.cli.exit_codes import RUNTIME_ERROR, SUCCESS
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.input.loader import load_snapshot

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Mode 1: file
# ---------------------------------------------------------------------------


def test_load_snapshot_from_file_returns_dict(tmp_path):
    snap, source = load_snapshot(str(FIXTURES / "cja_snapshot_clean.json"))
    assert snap["metadata"]["Data View ID"] == "dv_clean_prod_web"
    assert source.endswith("cja_snapshot_clean.json")


# ---------------------------------------------------------------------------
# Mode 2: directory
# ---------------------------------------------------------------------------


def test_load_snapshot_from_directory_picks_latest_by_filename_timestamp(tmp_path):
    early = json.loads((FIXTURES / "cja_snapshot_clean.json").read_text())
    late = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text())
    (tmp_path / "snapshot_2026-04-01.json").write_text(json.dumps(early))
    (tmp_path / "snapshot_2026-04-25.json").write_text(json.dumps(late))
    snap, source = load_snapshot(str(tmp_path))
    assert snap["metadata"]["Data View ID"] == "dv_messy_prod_web"
    assert source.endswith("snapshot_2026-04-25.json")


def test_load_snapshot_with_at_picks_latest_not_after_target(tmp_path):
    early = json.loads((FIXTURES / "cja_snapshot_clean.json").read_text())
    late = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text())
    (tmp_path / "snapshot_2026-04-01.json").write_text(json.dumps(early))
    (tmp_path / "snapshot_2026-04-25.json").write_text(json.dumps(late))
    snap, _ = load_snapshot(str(tmp_path), at="2026-04-15")
    assert snap["metadata"]["Data View ID"] == "dv_clean_prod_web"


def test_load_snapshot_with_at_no_matches_raises(tmp_path):
    (tmp_path / "snapshot_2026-05-01.json").write_text(
        (FIXTURES / "cja_snapshot_clean.json").read_text()
    )
    with pytest.raises(InvalidSnapshotError, match="at or before"):
        load_snapshot(str(tmp_path), at="2026-04-01")


def test_load_snapshot_empty_directory_raises(tmp_path):
    with pytest.raises(InvalidSnapshotError, match="no .json snapshots"):
        load_snapshot(str(tmp_path))


# ---------------------------------------------------------------------------
# Mode 4: stdin
# ---------------------------------------------------------------------------


def test_load_snapshot_from_stdin(monkeypatch):
    payload = (FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    snap, source = load_snapshot("-")
    assert snap["metadata"]["Data View ID"] == "dv_clean_prod_web"
    assert source == "stdin"


def test_load_snapshot_empty_stdin_raises(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(InvalidSnapshotError, match="empty"):
        load_snapshot("-")


# ---------------------------------------------------------------------------
# CLI dispatch across modes
# ---------------------------------------------------------------------------


def test_cli_directory_mode(tmp_path):
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    shutil.copy(FIXTURES / "cja_snapshot_messy.json", snap_dir / "snapshot_2026-04-25.json")
    rc = main([
        str(snap_dir),
        "--output", str(tmp_path / "out.html"),
        "--quiet",
    ])
    assert rc == SUCCESS


def test_cli_stdin_mode(tmp_path, monkeypatch, capsys):
    payload = (FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    rc = main(["-", "--output", str(tmp_path / "out.html"), "--quiet"])
    assert rc == SUCCESS


def test_cli_rejects_no_input(capsys):
    rc = main([])
    assert rc == RUNTIME_ERROR
    assert "no input specified" in capsys.readouterr().err


def test_cli_rejects_multiple_input_modes(tmp_path, capsys):
    rc = main([
        str(FIXTURES / "cja_snapshot_messy.json"),
        "--dataview", "dv_test",
        "--output", str(tmp_path / "out.html"),
    ])
    assert rc == RUNTIME_ERROR
    assert "multiple input modes" in capsys.readouterr().err


def test_cli_dataview_requires_cja_auto_sdr_on_path(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    rc = main([
        "--dataview", "dv_test",
        "--output", str(tmp_path / "out.html"),
    ])
    assert rc == RUNTIME_ERROR
    assert "cja_auto_sdr not found" in capsys.readouterr().err


def test_cli_rsid_uses_aa_adapter(tmp_path, capsys):
    """Mock shell_aa to inject an AA snapshot — exercises Mode 3 wiring."""
    aa_payload = json.loads((FIXTURES / "aa_snapshot_messy.json").read_text(encoding="utf-8"))

    def fake_shell_aa(rsid, *, extra_args=None):
        return aa_payload, f"shell-out:aa_auto_sdr {rsid}"

    with patch("sdr_grader.cli.main.shell_aa", side_effect=fake_shell_aa):
        rc = main([
            "--rsid", "messy.prod",
            "--output", str(tmp_path / "out.html"),
            "--quiet",
        ])
    assert rc == SUCCESS

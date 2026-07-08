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


def test_directory_pick_prefers_fresh_untimestamped_file(tmp_path):
    import os

    stale = tmp_path / "snapshot_2020-01-01.json"
    stale.write_text('{"which": "stale"}', encoding="utf-8")
    fresh = tmp_path / "latest.json"
    fresh.write_text('{"which": "fresh"}', encoding="utf-8")
    old = 946684800  # 2000-01-01, keeps the mtime comparison unambiguous
    os.utime(stale, (old, old))

    snapshot, _source = load_snapshot(str(tmp_path))
    assert snapshot == {"which": "fresh"}


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
    rc = main(
        [
            str(snap_dir),
            "--output",
            str(tmp_path / "out.html"),
            "--quiet",
        ]
    )
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
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--dataview",
            "dv_test",
            "--output",
            str(tmp_path / "out.html"),
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "multiple input modes" in capsys.readouterr().err


def test_cli_dataview_requires_cja_auto_sdr_on_path(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    rc = main(
        [
            "--dataview",
            "dv_test",
            "--output",
            str(tmp_path / "out.html"),
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "cja_auto_sdr not found" in capsys.readouterr().err


def test_shell_cja_passes_include_all_inventory(monkeypatch):
    """CJA shell-out must request the full inventory so calc-metric and
    segment rule packs grade against populated inputs."""
    import subprocess

    from sdr_grader.input.shell_out import shell_cja

    captured: dict = {}

    class _FakeCompleted:
        stdout = "{}"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompleted()

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    snapshot, source = shell_cja("dv_test")
    assert snapshot == {}
    assert source == "shell-out:cja_auto_sdr dv_test"
    assert "--include-all-inventory" in captured["cmd"]
    # Flag must precede --output so cja_auto_sdr applies it to the JSON write.
    assert captured["cmd"].index("--include-all-inventory") < captured["cmd"].index("--output")


def test_shell_cja_raises_when_subprocess_exits_nonzero(monkeypatch):
    """Upstream tool exiting non-zero must surface as InvalidSnapshotError
    carrying the captured stderr."""
    import subprocess

    from sdr_grader.core.exceptions import InvalidSnapshotError
    from sdr_grader.input.shell_out import shell_cja

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=2, cmd=cmd, output="", stderr="auth token expired"
        )

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InvalidSnapshotError, match="auth token expired"):
        shell_cja("dv_test")


def test_shell_cja_raises_when_binary_missing_at_invocation(monkeypatch):
    """shutil.which returned a path but the binary vanished before exec —
    surface as InvalidSnapshotError, not a raw FileNotFoundError."""
    import subprocess

    from sdr_grader.core.exceptions import InvalidSnapshotError
    from sdr_grader.input.shell_out import shell_cja

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InvalidSnapshotError, match="could not be invoked"):
        shell_cja("dv_test")


def test_shell_cja_raises_on_non_json_stdout(monkeypatch):
    """Upstream succeeded but wrote garbage to stdout — fail loudly rather
    than handing malformed input to the adapter."""
    import subprocess

    from sdr_grader.core.exceptions import InvalidSnapshotError
    from sdr_grader.input.shell_out import shell_cja

    class _Completed:
        stdout = "not json at all"
        stderr = ""

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Completed())

    with pytest.raises(InvalidSnapshotError, match="not valid JSON"):
        shell_cja("dv_test")


def test_cli_rsid_uses_aa_adapter(tmp_path, capsys):
    """Mock shell_aa to inject an AA snapshot — exercises Mode 3 wiring."""
    aa_payload = json.loads((FIXTURES / "aa_snapshot_messy.json").read_text(encoding="utf-8"))

    def fake_shell_aa(rsid, *, extra_args=None):
        return aa_payload, f"shell-out:aa_auto_sdr {rsid}"

    with patch("sdr_grader.cli.main.shell_aa", side_effect=fake_shell_aa):
        rc = main(
            [
                "--rsid",
                "messy.prod",
                "--output",
                str(tmp_path / "out.html"),
                "--quiet",
            ]
        )
    assert rc == SUCCESS


def test_shell_out_passes_timeout_and_encoding_and_surfaces_warnings(monkeypatch, capsys):
    import subprocess as sp

    from sdr_grader.input import shell_out

    seen_kwargs = {}

    def fake_run(cmd, **kwargs):
        seen_kwargs.update(kwargs)
        return sp.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="token expires soon\n")

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "run", fake_run)

    snapshot, source = shell_out.shell_cja("dv_123")
    assert snapshot == {"ok": True}
    assert seen_kwargs["timeout"] == shell_out.SHELL_OUT_TIMEOUT_SECONDS
    assert seen_kwargs["encoding"] == "utf-8"
    assert "token expires soon" in capsys.readouterr().err


def test_shell_out_timeout_raises_invalid_snapshot(monkeypatch):
    import subprocess as sp

    from sdr_grader.input import shell_out

    def fake_run(cmd, **kwargs):
        raise sp.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "run", fake_run)

    with pytest.raises(InvalidSnapshotError, match="did not finish"):
        shell_out.shell_cja("dv_123")


def test_shell_out_undecodable_bytes_raises_invalid_snapshot(monkeypatch):
    from sdr_grader.input import shell_out

    def fake_run(cmd, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "run", fake_run)

    with pytest.raises(InvalidSnapshotError, match="could not be decoded as UTF-8"):
        shell_out.shell_cja("dv_123")


def test_load_file_with_utf8_bom(tmp_path):
    p = tmp_path / "snap.json"
    p.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    snapshot, _source = load_snapshot(str(p))
    assert snapshot == {"a": 1}

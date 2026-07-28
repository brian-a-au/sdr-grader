"""Tests for input/loader.py and CLI input-mode dispatch."""

from __future__ import annotations

import io
import json
import shutil
import sys
from datetime import UTC, datetime
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


def test_load_snapshot_rejects_missing_path(tmp_path):
    missing = tmp_path / "missing.json"

    with pytest.raises(InvalidSnapshotError, match=f"snapshot path not found: {missing}"):
        load_snapshot(str(missing))


def test_load_snapshot_wraps_file_read_error(tmp_path, monkeypatch):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_target_read(path, *args, **kwargs):
        if path == snapshot_path:
            raise OSError("simulated read failure")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_target_read)

    with pytest.raises(InvalidSnapshotError, match="simulated read failure") as exc_info:
        load_snapshot(str(snapshot_path))
    assert str(snapshot_path) in str(exc_info.value)


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


def test_load_snapshot_rejects_invalid_at_timestamp(tmp_path):
    (tmp_path / "snapshot_2026-04-01.json").write_text("{}", encoding="utf-8")

    with pytest.raises(InvalidSnapshotError, match="not a recognized timestamp"):
        load_snapshot(str(tmp_path), at="not-a-date")


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


def test_directory_candidate_timestamps_are_utc_aware(tmp_path):
    """Issue #18: an mtime is an epoch instant, not naive local wall time."""
    import os

    from sdr_grader.input.loader import _candidate_timestamp

    untimestamped = tmp_path / "latest.json"
    untimestamped.write_text("{}", encoding="utf-8")
    epoch = 946684800  # 2000-01-01T00:00:00Z
    os.utime(untimestamped, (epoch, epoch))

    timestamped = tmp_path / "snapshot_2000-01-02.json"
    timestamped.write_text("{}", encoding="utf-8")

    assert _candidate_timestamp(untimestamped) == datetime(
        2000,
        1,
        1,
        tzinfo=UTC,
    )
    assert _candidate_timestamp(timestamped) == datetime(
        2000,
        1,
        2,
        tzinfo=UTC,
    )


def test_directory_invalid_filename_timestamp_falls_back_to_mtime(tmp_path):
    import os

    valid = tmp_path / "snapshot_2000-01-01.json"
    valid.write_text('{"which": "valid timestamp"}', encoding="utf-8")
    invalid = tmp_path / "snapshot_2026-99-99.json"
    invalid.write_text('{"which": "mtime fallback"}', encoding="utf-8")
    os.utime(valid, (946684800, 946684800))

    snapshot, source = load_snapshot(str(tmp_path))

    assert snapshot == {"which": "mtime fallback"}
    assert source == str(invalid)


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


def test_load_snapshot_invalid_stdin_json_raises(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))

    with pytest.raises(InvalidSnapshotError, match="stdin is not valid JSON"):
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


class _FakeShellProcess:
    def __init__(
        self,
        cmd,
        *,
        stdout: bytes = b"{}",
        stderr: bytes = b"",
        returncode: int = 0,
        timeout_once: bool = False,
    ):
        self.cmd = cmd
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.running = timeout_once
        self.pid = 999_999

    def poll(self):
        return None if self.running else self.returncode

    def wait(self):
        return self.returncode

    def kill(self):
        self.running = False
        self.returncode = -9


def test_shell_cja_passes_include_all_inventory(monkeypatch):
    """CJA shell-out must request the full inventory so calc-metric and
    segment rule packs grade against populated inputs."""
    from sdr_grader.input import shell_out

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeShellProcess(cmd)

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    snapshot, source = shell_out.shell_cja("dv_test")
    assert snapshot == {}
    assert source == "shell-out:cja_auto_sdr"
    assert "--include-all-inventory" in captured["cmd"]
    # Flag must precede --output so cja_auto_sdr applies it to the JSON write.
    assert captured["cmd"].index("--include-all-inventory") < captured["cmd"].index("--output")


def test_shell_aa_builds_report_suite_command_with_extra_args(monkeypatch):
    from sdr_grader.input import shell_out

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeShellProcess(cmd, stdout=b'{"ok": true}')

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    snapshot, source = shell_out.shell_aa(
        "prod.rsid", extra_args=["--company", "acme"]
    )

    assert snapshot == {"ok": True}
    assert source == "shell-out:aa_auto_sdr"
    assert captured["cmd"] == [
        "/usr/bin/aa_auto_sdr",
        "prod.rsid",
        "--format",
        "json",
        "--output",
        "-",
        "--company",
        "acme",
    ]


def test_shell_cja_raises_when_subprocess_exits_nonzero(monkeypatch):
    """Upstream failures expose status, never captured child diagnostics."""
    from sdr_grader.input import shell_out

    def fake_popen(cmd, **kwargs):
        return _FakeShellProcess(
            cmd, returncode=2, stderr=b"PRIVATE auth token expired"
        )

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    with pytest.raises(InvalidSnapshotError, match=r"child-exit.*status 2") as raised:
        shell_out.shell_cja("dv_test")
    assert "auth token" not in str(raised.value)


def test_shell_cja_raises_when_binary_missing_at_invocation(monkeypatch):
    """shutil.which returned a path but the binary vanished before exec —
    surface as InvalidSnapshotError, not a raw FileNotFoundError."""
    from sdr_grader.input import shell_out

    def fake_popen(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    with pytest.raises(InvalidSnapshotError, match=r"invoke-failed"):
        shell_out.shell_cja("dv_test")


def test_shell_cja_raises_on_non_json_stdout(monkeypatch):
    """Upstream succeeded but wrote garbage to stdout — fail loudly rather
    than handing malformed input to the adapter."""
    from sdr_grader.input import shell_out

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        shell_out.subprocess,
        "Popen",
        lambda cmd, **kw: _FakeShellProcess(cmd, stdout=b"not json at all"),
    )

    with pytest.raises(InvalidSnapshotError, match=r"invalid-json"):
        shell_out.shell_cja("dv_test")


def test_cli_rsid_uses_aa_adapter(tmp_path, capsys):
    """Mock shell_aa to inject an AA snapshot — exercises Mode 3 wiring."""
    aa_payload = json.loads((FIXTURES / "aa_snapshot_messy.json").read_text(encoding="utf-8"))

    def fake_shell_aa(rsid, *, extra_args=None):
        return aa_payload, "shell-out:aa_auto_sdr"

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


def test_shell_out_uses_bounded_pipes_and_surfaces_warnings(monkeypatch, capsys):
    from sdr_grader.input import shell_out

    process = _FakeShellProcess(
        [],
        stdout=b'{"ok": true}',
        stderr=b"PRIVATE token expires soon\n",
    )

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", lambda cmd, **kwargs: process)

    snapshot, source = shell_out.shell_cja("dv_123")
    assert snapshot == {"ok": True}
    diagnostics = capsys.readouterr().err
    assert "shell-child-diagnostics" in diagnostics
    assert "token expires soon" not in diagnostics


def test_shell_out_timeout_raises_invalid_snapshot(monkeypatch):
    from sdr_grader.input import shell_out

    process = _FakeShellProcess([], timeout_once=True)

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", lambda cmd, **kwargs: process)
    monkeypatch.setattr(shell_out, "SHELL_OUT_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(InvalidSnapshotError, match=r"shell error \[timeout\]"):
        shell_out.shell_cja("dv_123")


def test_shell_out_undecodable_bytes_raises_invalid_snapshot(monkeypatch):
    from sdr_grader.input import shell_out

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(
        shell_out.subprocess,
        "Popen",
        lambda cmd, **kwargs: _FakeShellProcess(cmd, stdout=b"\x80"),
    )

    with pytest.raises(InvalidSnapshotError, match=r"invalid-encoding"):
        shell_out.shell_cja("dv_123")


def test_load_file_with_utf8_bom(tmp_path):
    p = tmp_path / "snap.json"
    p.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    snapshot, _source = load_snapshot(str(p))
    assert snapshot == {"a": 1}

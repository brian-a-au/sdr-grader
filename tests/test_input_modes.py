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


def _write_cja_json_output(cmd: list[str], content: str | bytes) -> Path:
    output_dir = Path(cmd[cmd.index("--output-dir") + 1])
    encoded = content.encode("utf-8") if isinstance(content, str) else content
    (output_dir / "current.json").write_bytes(encoded)
    return output_dir


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


def test_file_json_recursion_error_is_domain_error(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")

    def recurse(_value):
        raise RecursionError("decoder recursion")

    monkeypatch.setattr("sdr_grader.input.loader.json.loads", recurse)

    with pytest.raises(InvalidSnapshotError, match="JSON exceeds nesting limits"):
        load_snapshot(str(snapshot))


def test_stdin_json_recursion_error_is_domain_error(monkeypatch):
    def recurse(_value):
        raise RecursionError("decoder recursion")

    monkeypatch.setattr("sdr_grader.input.loader.json.loads", recurse)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    with pytest.raises(InvalidSnapshotError, match="stdin JSON exceeds nesting limits"):
        load_snapshot("-")


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


def test_list_snapshot_candidates_returns_complete_sorted_json_set(tmp_path):
    from sdr_grader.input.loader import list_snapshot_candidates

    assert list_snapshot_candidates(tmp_path) == []

    expected = [tmp_path / "a.json", tmp_path / "b.json"]
    for path in [expected[1], tmp_path / "ignored.txt", expected[0]]:
        path.write_text("{}", encoding="utf-8")

    assert list_snapshot_candidates(tmp_path) == expected


def test_list_snapshot_candidates_wraps_discovery_errors(tmp_path, monkeypatch):
    from sdr_grader.input.loader import list_snapshot_candidates

    def fail_glob(_path, _pattern):
        raise OSError("simulated discovery failure")

    monkeypatch.setattr(Path, "glob", fail_glob)

    with pytest.raises(InvalidSnapshotError, match="could not inspect snapshot directory"):
        list_snapshot_candidates(tmp_path)


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


def test_mtime_cutoff_selection_is_timezone_independent(tmp_path):
    import os
    import time

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text('{"chosen": "before"}', encoding="utf-8")
    after.write_text('{"chosen": "after"}', encoding="utf-8")
    os.utime(before, (1767265200, 1767265200))  # 2026-01-01T11:00:00Z
    os.utime(after, (1767272400, 1767272400))  # 2026-01-01T13:00:00Z
    original_tz = os.environ.get("TZ")
    selected = []
    try:
        for zone in ("UTC", "America/Los_Angeles", "Pacific/Auckland"):
            os.environ["TZ"] = zone
            time.tzset()
            snapshot, _source = load_snapshot(
                str(tmp_path),
                at="2026-01-01T07:00:00-05:00",
            )
            selected.append(snapshot["chosen"])
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()

    assert selected == ["before", "before", "before"]


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


def test_shell_cja_builds_complete_inventory_command_with_extra_args(monkeypatch):
    """CJA shell-out must request the full inventory so calc-metric and
    segment rule packs grade against populated inputs."""
    from sdr_grader.input import shell_out

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        captured["output_dir"] = _write_cja_json_output(cmd, "{}")
        return _FakeShellProcess(cmd, stdout=b"SDR JSON written to disk\n")

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    snapshot, source = shell_out.shell_cja(
        "dv_test",
        extra_args=["--log-level", "debug"],
    )
    assert snapshot == {}
    assert source == "shell-out:cja_auto_sdr"
    assert captured["cmd"] == [
        "/usr/bin/cja_auto_sdr",
        "dv_test",
        "--format",
        "json",
        "--output-dir",
        str(captured["output_dir"]),
        "--include-all-inventory",
        "--quiet",
        "--log-level",
        "debug",
    ]
    assert not captured["output_dir"].exists()
    assert captured["cmd"].count("--include-all-inventory") == 1
    assert captured["cmd"].count("--quiet") == 1


def test_shell_cja_json_recursion_error_is_domain_error(monkeypatch):
    from sdr_grader.input import shell_out

    def fake_popen(cmd, **_kwargs):
        _write_cja_json_output(cmd, "{}")
        return _FakeShellProcess(cmd, stdout=b"SDR JSON written to disk\n")

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        shell_out.subprocess,
        "Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        shell_out.json,
        "loads",
        lambda _value: (_ for _ in ()).throw(RecursionError("decoder recursion")),
    )

    with pytest.raises(InvalidSnapshotError, match="invalid-json-depth"):
        shell_out.shell_cja("dv_test")


def test_shell_aa_builds_report_suite_command_with_extra_args(monkeypatch):
    from sdr_grader.input import shell_out

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeShellProcess(cmd, stdout=b'{"ok": true}')

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    snapshot, source = shell_out.shell_aa("prod.rsid", extra_args=["--company", "acme"])

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
        return _FakeShellProcess(cmd, returncode=2, stderr=b"PRIVATE auth token expired")

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


def test_shell_cja_raises_on_non_json_output(monkeypatch):
    """Upstream succeeded but wrote garbage to its JSON artifact — fail loudly
    rather than handing malformed input to the adapter."""
    from sdr_grader.input import shell_out

    captured = {}

    def fake_popen(cmd, **_kwargs):
        captured["output_dir"] = _write_cja_json_output(cmd, "not json at all")
        return _FakeShellProcess(cmd, stdout=b"SDR JSON written to disk\n")

    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        shell_out.subprocess,
        "Popen",
        fake_popen,
    )

    with pytest.raises(InvalidSnapshotError, match=r"invalid-json"):
        shell_out.shell_cja("dv_test")
    assert not captured["output_dir"].exists()


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

    def fake_popen(cmd, **_kwargs):
        _write_cja_json_output(cmd, '{"ok": true}')
        return _FakeShellProcess(
            cmd,
            stdout=b"SDR JSON written to disk\n",
            stderr=b"PRIVATE token expires soon\n",
        )

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    snapshot, source = shell_out.shell_cja("dv_123")
    assert snapshot == {"ok": True}
    diagnostics = capsys.readouterr().err
    assert "shell-child-diagnostics" in diagnostics
    assert "token expires soon" not in diagnostics


@pytest.mark.parametrize("output_count", [0, 2])
def test_shell_cja_requires_exactly_one_generated_json(monkeypatch, output_count):
    from sdr_grader.input import shell_out

    captured = {}

    def fake_popen(cmd, **_kwargs):
        output_dir = Path(cmd[cmd.index("--output-dir") + 1])
        captured["output_dir"] = output_dir
        for index in range(output_count):
            (output_dir / f"{index}.json").write_text("{}", encoding="utf-8")
        return _FakeShellProcess(cmd, stdout=b"SDR JSON written to disk\n")

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    with pytest.raises(InvalidSnapshotError, match=rf"output-count.*produced {output_count}"):
        shell_out.shell_cja("dv_123")
    assert not captured["output_dir"].exists()


def test_shell_cja_output_inspection_error_is_domain_error(monkeypatch):
    from sdr_grader.input import shell_out

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(
        shell_out.subprocess,
        "Popen",
        lambda cmd, **_kwargs: _FakeShellProcess(
            cmd,
            stdout=b"SDR JSON written to disk\n",
        ),
    )

    def fail_glob(_path, _pattern):
        raise PermissionError("inspection denied")

    monkeypatch.setattr(Path, "glob", fail_glob)

    with pytest.raises(InvalidSnapshotError, match="JSON output could not be inspected"):
        shell_out.shell_cja("dv_123")


def test_shell_cja_output_read_error_is_domain_error(monkeypatch):
    from sdr_grader.input import shell_out

    def fail_open(_path, *_args, **_kwargs):
        raise PermissionError("read denied")

    def fake_popen(cmd, **_kwargs):
        _write_cja_json_output(cmd, "{}")
        monkeypatch.setattr(Path, "open", fail_open)
        return _FakeShellProcess(cmd, stdout=b"SDR JSON written to disk\n")

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)

    with pytest.raises(InvalidSnapshotError, match=r"io-failed.*could not be read"):
        shell_out.shell_cja("dv_123")


def test_shell_cja_generated_json_respects_output_limit(monkeypatch):
    from sdr_grader.input import shell_out

    def fake_popen(cmd, **_kwargs):
        _write_cja_json_output(cmd, b"12345")
        return _FakeShellProcess(cmd, stdout=b"")

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(shell_out.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(shell_out, "MAX_STDOUT_BYTES", 4)

    with pytest.raises(InvalidSnapshotError, match=r"output-limit.*JSON output"):
        shell_out.shell_cja("dv_123")


def test_shell_cja_temporary_output_error_is_domain_error(monkeypatch):
    from sdr_grader.input import shell_out

    def fail_temporary_directory(**_kwargs):
        raise PermissionError("temporary directory denied")

    monkeypatch.setattr(shell_out.tempfile, "TemporaryDirectory", fail_temporary_directory)

    with pytest.raises(InvalidSnapshotError, match=r"temporary-output"):
        shell_out.shell_cja("dv_123")


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

    def fake_popen(cmd, **_kwargs):
        _write_cja_json_output(cmd, b"\x80")
        return _FakeShellProcess(cmd, stdout=b"SDR JSON written to disk\n")

    monkeypatch.setattr(shell_out.shutil, "which", lambda tool: f"/fake/{tool}")
    monkeypatch.setattr(
        shell_out.subprocess,
        "Popen",
        fake_popen,
    )

    with pytest.raises(InvalidSnapshotError, match=r"invalid-encoding"):
        shell_out.shell_cja("dv_123")


def test_load_file_with_utf8_bom(tmp_path):
    p = tmp_path / "snap.json"
    p.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    snapshot, _source = load_snapshot(str(p))
    assert snapshot == {"a": 1}

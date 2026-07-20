import runpy
import tomllib
from pathlib import Path

import pytest

from sdr_grader import __version__


def test_package_importable():
    assert isinstance(__version__, str)


def test_sdist_excludes_local_claude_workspaces():
    """Local agent worktrees must never ship in the public source archive."""
    repo_root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    excludes = config["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert "/.claude" in excludes


@pytest.mark.parametrize("exit_code", [0, 2])
def test_module_entry_point_propagates_cli_exit_code(monkeypatch, exit_code):
    monkeypatch.setattr("sdr_grader.cli.main.main", lambda: exit_code)
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("sdr_grader.__main__", run_name="__main__")
    assert exc_info.value.code == exit_code

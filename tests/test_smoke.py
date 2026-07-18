import tomllib
from pathlib import Path

from sdr_grader import __version__


def test_package_importable():
    assert isinstance(__version__, str)


def test_sdist_excludes_local_claude_workspaces():
    """Local agent worktrees must never ship in the public source archive."""
    repo_root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    excludes = config["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert "/.claude" in excludes

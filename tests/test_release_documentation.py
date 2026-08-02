"""Release-facing documentation invariants."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_readme_keeps_live_test_badge_without_fixed_numeric_count():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "actions/workflows/test.yml/badge.svg" in readme
    assert not re.search(r"shields\.io/badge/tests-[0-9]", readme)

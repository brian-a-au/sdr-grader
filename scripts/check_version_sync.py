"""Fail if the package version and the CHANGELOG disagree.

The build reads its version from ``src/sdr_grader/__init__.py`` (single
source since 1.1.1), so the remaining thing that can drift is the
CHANGELOG: a release commit must add a ``## <version>`` entry that
matches ``__version__``. Runs on plain python3 with no dependencies so
CI can call it without syncing the project.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    init_text = (ROOT / "src" / "sdr_grader" / "__init__.py").read_text(
        encoding="utf-8"
    )
    init_match = re.search(r'^__version__ = "([^"]+)"', init_text, re.MULTILINE)
    if not init_match:
        print("error: no __version__ in src/sdr_grader/__init__.py")
        return 1

    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    changelog_match = re.search(r"^## (\S+)", changelog_text, re.MULTILINE)
    if not changelog_match:
        print("error: no '## <version>' heading in CHANGELOG.md")
        return 1

    package = init_match.group(1)
    changelog = changelog_match.group(1)
    if package != changelog:
        print(
            f"error: __version__ is {package} but the top CHANGELOG entry "
            f"is {changelog}"
        )
        return 1

    print(f"version sync ok: {package}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

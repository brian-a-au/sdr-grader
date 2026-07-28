"""Fail if the package version and the CHANGELOG disagree.

The build reads its version from ``src/sdr_grader/__init__.py`` (single
source since 1.1.1), so the remaining thing that can drift is the
CHANGELOG: a release commit must add a ``## <version>`` entry that
matches ``__version__``. Runs on plain python3 with no dependencies so
CI can call it without syncing the project.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(root: Path = ROOT) -> int:
    init_text = (root / "src" / "sdr_grader" / "__init__.py").read_text(
        encoding="utf-8"
    )
    init_match = re.search(r'^__version__ = "([^"]+)"', init_text, re.MULTILINE)
    if not init_match:
        print("error: no __version__ in src/sdr_grader/__init__.py")
        return 1

    changelog_text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    changelog_match = re.search(r"^## (\S+)", changelog_text, re.MULTILINE)
    if not changelog_match:
        print("error: no '## <version>' heading in CHANGELOG.md")
        return 1

    package = init_match.group(1)
    changelog = changelog_match.group(1)
    try:
        plugin = json.loads(
            (root / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        marketplace = json.loads(
            (root / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read plugin release metadata: {exc}")
        return 1
    if not isinstance(plugin, dict) or not isinstance(marketplace, dict):
        print("error: plugin and marketplace manifests must be JSON objects")
        return 1
    marketplace_plugins = marketplace.get("plugins") or []
    if not isinstance(marketplace_plugins, list) or not all(
        isinstance(entry, dict) for entry in marketplace_plugins
    ):
        print("error: marketplace plugins must be a list of JSON objects")
        return 1
    marketplace_plugin = next(
        (
            entry
            for entry in marketplace_plugins
            if entry.get("name") == "sdr-grader"
        ),
        {},
    )
    versions = {
        "package": package,
        "CHANGELOG": changelog,
        "plugin manifest": plugin.get("version"),
        "marketplace": marketplace_plugin.get("version"),
    }
    if not all(isinstance(value, str) for value in versions.values()):
        details = ", ".join(f"{name}={value!r}" for name, value in versions.items())
        print(f"error: release versions must be strings: {details}")
        return 1
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={value!r}" for name, value in versions.items())
        print(f"error: release versions disagree: {details}")
        return 1
    if marketplace_plugin.get("source") != "./":
        print("error: sdr-grader marketplace source must be './'")
        return 1

    print(f"version sync ok: package/plugin/marketplace {package}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

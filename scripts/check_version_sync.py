"""Validate the complete source-side release identity without dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
PACK_VERSION_PATTERN = re.compile(
    r'^version:\s*["\']?([^"\'#\s]+)',
    re.MULTILINE,
)


def main(root: Path = ROOT, *, tag: str | None = None) -> int:
    try:
        init_text = (root / "src" / "sdr_grader" / "__init__.py").read_text(
            encoding="utf-8"
        )
        changelog_text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: could not read release identity source: {exc}")
        return 1
    init_match = re.search(r'^__version__ = "([^"]+)"', init_text, re.MULTILINE)
    if not init_match:
        print("error: no __version__ in src/sdr_grader/__init__.py")
        return 1

    changelog_match = re.search(r"^## (\S+)", changelog_text, re.MULTILINE)
    if not changelog_match:
        print("error: no '## <version>' heading in CHANGELOG.md")
        return 1

    package = init_match.group(1)
    changelog = changelog_match.group(1)
    if not VERSION_PATTERN.fullmatch(package):
        print(f"error: package version is not X.Y.Z: {package!r}")
        return 1
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

    if tag is not None and tag != f"v{package}":
        print(
            f"error: release tag must be exactly v{package}, got {tag!r}"
        )
        return 1

    pack_versions: dict[str, str] = {}
    for pack_name in ("strict", "pragmatic"):
        pack_path = (
            root
            / "src"
            / "sdr_grader"
            / "rules"
            / "packs"
            / pack_name
            / "_meta.yaml"
        )
        try:
            pack_text = pack_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: could not read {pack_name} pack metadata: {exc}")
            return 1
        match = PACK_VERSION_PATTERN.search(pack_text)
        if not match:
            print(f"error: no version in {pack_name} pack metadata")
            return 1
        pack_versions[pack_name] = match.group(1)
    if len(set(pack_versions.values())) != 1:
        details = ", ".join(
            f"{name}={version!r}"
            for name, version in pack_versions.items()
        )
        print(f"error: bundled pack versions disagree: {details}")
        return 1
    pack_version = pack_versions["strict"]

    report_examples = sorted((root / "examples").glob("grade-*.html"))
    if not report_examples:
        print("error: no generated grade report examples found")
        return 1
    package_marker = f"sdr-grader v{package}"
    pack_marker = f"@{pack_version}"
    for report_path in report_examples:
        try:
            report_text = report_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: could not read generated report footer: {exc}")
            return 1
        if package_marker not in report_text or pack_marker not in report_text:
            print(
                "error: generated report identity drift in "
                f"{report_path.name}; expected {package_marker} and "
                f"rubric {pack_marker}"
            )
            return 1

    print(
        "version sync ok: "
        f"package/plugin/marketplace {package}; packs {pack_version}"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tag",
        help="Release tag to verify; must be exactly v<package-version>.",
    )
    arguments = parser.parse_args()
    sys.exit(main(tag=arguments.tag))

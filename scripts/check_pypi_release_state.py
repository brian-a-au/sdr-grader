#!/usr/bin/env python3
"""Classify whether immutable candidate files already exist on PyPI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_METADATA_BYTES = 4 * 1024 * 1024


class ReleaseStateError(Exception):
    """PyPI state does not permit a safe, idempotent publication attempt."""


def classify_release_state(
    dist_dir: Path,
    metadata: dict[str, Any] | None,
) -> str:
    """Return absent, partial, or matching after verifying every remote digest."""
    candidates = _candidate_digests(dist_dir)
    if metadata is None:
        return "absent"
    remote = _remote_digests(metadata)
    if not remote:
        return "absent"
    unexpected = sorted(set(remote) - set(candidates))
    mismatched = sorted(
        name
        for name, digest in remote.items()
        if name in candidates and candidates[name] != digest
    )
    if unexpected or mismatched:
        raise ReleaseStateError(
            "PyPI already contains files outside this immutable candidate"
        )
    if remote == candidates:
        return "matching"
    return "partial"


def _candidate_digests(dist_dir: Path) -> dict[str, str]:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    try:
        entries = sorted(dist_dir.iterdir())
    except OSError as exc:
        raise ReleaseStateError("could not inspect immutable candidate files") from exc
    expected = wheels + sdists
    if len(wheels) != 1 or len(sdists) != 1 or entries != sorted(expected):
        raise ReleaseStateError(
            "candidate directory must contain exactly one wheel and one sdist"
        )
    try:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (wheels[0], sdists[0])
        }
    except OSError as exc:
        raise ReleaseStateError("could not read immutable candidate files") from exc


def _remote_digests(metadata: dict[str, Any]) -> dict[str, str]:
    urls = metadata.get("urls")
    if not isinstance(urls, list):
        raise ReleaseStateError("PyPI metadata has no release file list")
    remote: dict[str, str] = {}
    for entry in urls:
        if not isinstance(entry, dict):
            raise ReleaseStateError("PyPI metadata contains an invalid file entry")
        filename = entry.get("filename")
        digests = entry.get("digests")
        digest = digests.get("sha256") if isinstance(digests, dict) else None
        if (
            not isinstance(filename, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ReleaseStateError("PyPI metadata contains incomplete file identity")
        if filename in remote:
            raise ReleaseStateError("PyPI metadata contains duplicate file identity")
        remote[filename] = digest
    return remote


def _fetch_metadata(project: str, version: str) -> dict[str, Any] | None:
    project_part = urllib.parse.quote(project, safe="")
    version_part = urllib.parse.quote(version, safe="")
    url = f"https://pypi.org/pypi/{project_part}/{version_part}/json"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "sdr-grader-release-gate",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(MAX_METADATA_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ReleaseStateError(f"PyPI returned HTTP {exc.code}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ReleaseStateError("could not query PyPI release state") from exc
    if len(payload) > MAX_METADATA_BYTES:
        raise ReleaseStateError("PyPI release metadata exceeds the size limit")
    try:
        metadata = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseStateError("PyPI returned invalid release metadata") from exc
    if not isinstance(metadata, dict):
        raise ReleaseStateError("PyPI returned invalid release metadata")
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        metadata = _fetch_metadata(args.project, args.version)
        print(classify_release_state(args.dist_dir, metadata))
    except ReleaseStateError as exc:
        print(f"release state check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

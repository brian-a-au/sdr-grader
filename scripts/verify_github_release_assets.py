#!/usr/bin/env python3
"""Verify that a retained GitHub draft contains the exact tested release bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


class ReleaseAssetError(Exception):
    """The existing GitHub release is not a safe recovery target."""


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReleaseAssetError(f"could not read {path}") from exc


def verify_release_assets(
    *,
    release: dict[str, Any],
    evidence_path: Path,
    dist_dir: Path,
    expected_tag: str,
) -> None:
    """Fail unless the existing draft exactly matches the retained candidate."""
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseAssetError("could not read release evidence") from exc

    if release.get("tagName") != expected_tag:
        raise ReleaseAssetError("existing release has the wrong tag")
    if release.get("isDraft") is not True:
        raise ReleaseAssetError("existing release is not a draft")

    records = evidence.get("artifacts")
    assets_payload = release.get("assets")
    if not isinstance(records, list) or not isinstance(assets_payload, list):
        raise ReleaseAssetError("release metadata has an invalid shape")

    try:
        expected = {
            record["filename"]: {
                "size": record["size"],
                "digest": f"sha256:{record['sha256']}",
            }
            for record in records
        }
        expected[evidence_path.name] = {
            "size": evidence_path.stat().st_size,
            "digest": f"sha256:{_digest(evidence_path)}",
        }
        assets = {asset["name"]: asset for asset in assets_payload}
    except (KeyError, TypeError, OSError) as exc:
        raise ReleaseAssetError("release metadata has an invalid shape") from exc

    if len(assets) != len(assets_payload) or set(assets) != set(expected):
        raise ReleaseAssetError("existing release has the wrong asset inventory")
    for name, record in expected.items():
        asset = assets[name]
        if (
            asset.get("size") != record["size"]
            or asset.get("digest") != record["digest"]
        ):
            raise ReleaseAssetError(f"existing release asset mismatch: {name}")
    for record in records:
        try:
            path = dist_dir / record["filename"]
            size = record["size"]
            digest = record["sha256"]
        except (KeyError, TypeError) as exc:
            raise ReleaseAssetError("release evidence has an invalid shape") from exc
        try:
            actual_size = path.stat().st_size
        except OSError as exc:
            raise ReleaseAssetError(f"could not inspect {path}") from exc
        if actual_size != size or _digest(path) != digest:
            raise ReleaseAssetError(f"retained candidate mismatch: {path.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-metadata", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--expected-tag", required=True)
    args = parser.parse_args(argv)
    try:
        release = json.loads(args.release_metadata.read_text(encoding="utf-8"))
        if not isinstance(release, dict):
            raise ReleaseAssetError("release metadata has an invalid shape")
        verify_release_assets(
            release=release,
            evidence_path=args.evidence,
            dist_dir=args.dist_dir,
            expected_tag=args.expected_tag,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ReleaseAssetError) as exc:
        print(f"GitHub release asset check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

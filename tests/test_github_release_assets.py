"""Tests for fail-closed recovery of an existing GitHub draft release."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "verify_github_release_assets.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_github_release_assets_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release_assets = _load_script()


def _fixture(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    files = {
        "sdr_grader-1.2.3-py3-none-any.whl": b"wheel",
        "sdr_grader-1.2.3.tar.gz": b"sdist",
    }
    records = []
    for name, payload in files.items():
        path = dist / name
        path.write_bytes(payload)
        records.append(
            {
                "filename": name,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    evidence = tmp_path / "release-artifacts.json"
    evidence.write_text(json.dumps({"artifacts": records}), encoding="utf-8")
    assets = [
        {
            "name": record["filename"],
            "size": record["size"],
            "digest": f"sha256:{record['sha256']}",
        }
        for record in records
    ]
    assets.append(
        {
            "name": evidence.name,
            "size": evidence.stat().st_size,
            "digest": f"sha256:{hashlib.sha256(evidence.read_bytes()).hexdigest()}",
        }
    )
    release = {"tagName": "v1.2.3", "isDraft": True, "assets": assets}
    return dist, evidence, release


def _verify(dist: Path, evidence: Path, release: dict) -> None:
    release_assets.verify_release_assets(
        release=release,
        evidence_path=evidence,
        dist_dir=dist,
        expected_tag="v1.2.3",
    )


def test_existing_draft_accepts_exact_tested_assets(tmp_path):
    dist, evidence, release = _fixture(tmp_path)

    _verify(dist, evidence, release)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda release: release.update(tagName="v9.9.9"), "wrong tag"),
        (lambda release: release.update(isDraft=False), "not a draft"),
        (lambda release: release["assets"].pop(), "wrong asset inventory"),
        (
            lambda release: release["assets"][0].update(size=999),
            "asset mismatch",
        ),
        (
            lambda release: release["assets"][0].update(digest="sha256:" + "0" * 64),
            "asset mismatch",
        ),
    ],
)
def test_existing_release_rejects_unsafe_remote_state(tmp_path, mutate, message):
    dist, evidence, release = _fixture(tmp_path)
    unsafe = deepcopy(release)
    mutate(unsafe)

    with pytest.raises(release_assets.ReleaseAssetError, match=message):
        _verify(dist, evidence, unsafe)


def test_existing_release_rejects_changed_retained_candidate(tmp_path):
    dist, evidence, release = _fixture(tmp_path)
    (dist / "sdr_grader-1.2.3.tar.gz").write_bytes(b"changed")

    with pytest.raises(release_assets.ReleaseAssetError, match="candidate mismatch"):
        _verify(dist, evidence, release)


def test_main_fails_closed_on_invalid_release_json(tmp_path, capsys):
    metadata = tmp_path / "release.json"
    metadata.write_text("not-json", encoding="utf-8")

    assert (
        release_assets.main(
            [
                "--release-metadata",
                str(metadata),
                "--evidence",
                str(tmp_path / "evidence.json"),
                "--dist-dir",
                str(tmp_path / "dist"),
                "--expected-tag",
                "v1.2.3",
            ]
        )
        == 1
    )
    assert "asset check failed" in capsys.readouterr().err

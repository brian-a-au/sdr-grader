"""Tests for digest-gated PyPI release recovery."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_pypi_release_state.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_pypi_release_state_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release_state = _load_script()


def _candidate(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "sdr_grader-1.2.0-py3-none-any.whl"
    sdist = dist / "sdr_grader-1.2.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    return dist, {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (wheel, sdist)
    }


def _metadata(digests: dict[str, str]) -> dict:
    return {
        "urls": [
            {"filename": name, "digests": {"sha256": digest}}
            for name, digest in digests.items()
        ]
    }


def test_release_state_classifies_absent_partial_and_matching(tmp_path):
    dist, digests = _candidate(tmp_path)
    first_name = next(iter(digests))

    assert release_state.classify_release_state(dist, None) == "absent"
    assert (
        release_state.classify_release_state(
            dist,
            _metadata({first_name: digests[first_name]}),
        )
        == "partial"
    )
    assert release_state.classify_release_state(
        dist,
        _metadata(digests),
    ) == "matching"


@pytest.mark.parametrize(
    "remote",
    [
        {"sdr_grader-1.2.0-py3-none-any.whl": "0" * 64},
        {"unexpected.whl": "0" * 64},
    ],
)
def test_release_state_rejects_mismatched_or_unexpected_files(tmp_path, remote):
    dist, _digests = _candidate(tmp_path)

    with pytest.raises(
        release_state.ReleaseStateError,
        match="outside this immutable candidate",
    ):
        release_state.classify_release_state(dist, _metadata(remote))


def test_release_state_rejects_extra_candidate_files(tmp_path):
    dist, _digests = _candidate(tmp_path)
    (dist / "unreviewed.txt").write_text("extra", encoding="utf-8")

    with pytest.raises(
        release_state.ReleaseStateError,
        match="exactly one wheel and one sdist",
    ):
        release_state.classify_release_state(dist, None)

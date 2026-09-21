import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "config", ROOT / ".github/scripts/validate_release_soak_config.py"
)
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


def candidate(version="7.8.9"):
    return dict(
        schema_version=1,
        active=True,
        release=dict(
            version=version,
            tag=f"v{version}",
            commit="a" * 40,
            tag_object="b" * 40,
            wheel=dict(name=f"sdr_grader-{version}-py3-none-any.whl", sha256="c" * 64),
            sdist=dict(name=f"sdr_grader-{version}.tar.gz", sha256="d" * 64),
            evidence=dict(name="release-artifacts.json", sha256="e" * 64),
        ),
        companion=dict(applicable=False, reason="No companion launch claim"),
        monitor_commit="f" * 40,
        window_id="unique-window-123",
        start_at="2026-09-20T00:00:00Z",
        end_at="2026-09-22T00:00:00Z",
        issue_number=99,
        start_evidence_url="https://github.com/brian-a-au/sdr-grader/issues/99#issuecomment-12345",
        readiness_record=f"docs/releases/{version}-readiness.md",
    )


@pytest.mark.parametrize("version", ["7.8.9", "8.0.1"])
def test_accepts_independent_identities(version):
    env = MODULE.validate(candidate(version))
    assert env["GRADER_VERSION"] == version
    assert env["COMPANION_APPLICABLE"] == "false"


def test_ships_inactive():
    import json

    assert (
        MODULE.validate(json.loads((ROOT / ".github/release-soak/candidate.json").read_text()))
        == {}
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("active", "true"),
        ("schema_version", True),
        ("monitor_commit", "main"),
        ("window_id", "bad\nENV=x"),
        ("end_at", "2026-09-21T23:59:59Z"),
        ("start_evidence_url", "https://example.com/proof"),
        ("issue_number", True),
    ],
)
def test_rejects_bad_manifest(field, value):
    config = candidate()
    config[field] = value
    with pytest.raises(ValueError):
        MODULE.validate(config)


def test_rejects_mixed_asset_identity():
    config = candidate()
    config["release"]["wheel"]["name"] = "sdr_grader-1.0.0-py3-none-any.whl"
    with pytest.raises(ValueError):
        MODULE.validate(config)


def test_explicit_immutable_companion():
    import copy

    config = candidate()
    release = copy.deepcopy(config["release"])
    release["wheel"]["name"] = "sdr_visualizer-7.8.9-py3-none-any.whl"
    release["sdist"]["name"] = "sdr_visualizer-7.8.9.tar.gz"
    release["evidence"]["name"] = "SHA256SUMS"
    config["companion"] = {
        "applicable": True,
        "reason": "Claimed paired workflow",
        "release": release,
    }
    env = MODULE.validate(config)
    assert env["VISUALIZER_SUMS_SHA"] == "e" * 64
    assert env["COMPANION_APPLICABLE"] == "true"


@pytest.mark.parametrize("config", [None, [], "invalid", 1])
def test_wrong_top_level_shapes_fail(config):
    with pytest.raises(ValueError):
        MODULE.validate(config)

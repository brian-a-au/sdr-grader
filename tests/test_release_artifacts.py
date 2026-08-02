from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_release_artifacts.py"
VERSION = "1.2.1"
SDIST_ROOT = f"sdr_grader-{VERSION}"
DIST_INFO = f"sdr_grader-{VERSION}.dist-info"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_release_artifacts",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_files(source_root: Path) -> dict[str, bytes]:
    package_files = {
        path.relative_to(source_root / "src").as_posix(): path.read_bytes()
        for path in (source_root / "src" / "sdr_grader").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }
    plugin_files = {
        "sdr_grader/plugin/.claude-plugin/plugin.json": (
            source_root / ".claude-plugin" / "plugin.json"
        ).read_bytes(),
        "sdr_grader/plugin/.claude-plugin/marketplace.json": (
            source_root / ".claude-plugin" / "marketplace.json"
        ).read_bytes(),
    }
    for path in (source_root / "skills" / "sdr-grader").rglob("*"):
        if path.is_file():
            relative = path.relative_to(source_root / "skills").as_posix()
            plugin_files[f"sdr_grader/plugin/skills/{relative}"] = path.read_bytes()
    return package_files | plugin_files


def _write_candidate(
    dist_dir: Path,
    *,
    forbidden_member: str | None = None,
    metadata_version: str = VERSION,
) -> tuple[Path, Path]:
    source_files = _source_files(REPO_ROOT)
    wheel = dist_dir / f"sdr_grader-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, payload in source_files.items():
            archive.writestr(name, payload)
        archive.writestr(
            f"{DIST_INFO}/METADATA",
            f"Metadata-Version: 2.4\nName: sdr-grader\nVersion: {metadata_version}\n",
        )
        archive.writestr(
            f"{DIST_INFO}/entry_points.txt",
            "[console_scripts]\nsdr-grader = sdr_grader.cli.main:main\n",
        )
        archive.writestr(f"{DIST_INFO}/WHEEL", "Root-Is-Purelib: true\n")
        archive.writestr(f"{DIST_INFO}/RECORD", "")
        if forbidden_member:
            archive.writestr(forbidden_member, "PRIVATE")

    sdist = dist_dir / f"sdr_grader-{VERSION}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        sdist_files = {
            f"{SDIST_ROOT}/src/{name}": payload
            for name, payload in source_files.items()
            if not name.startswith("sdr_grader/plugin/")
        }
        for path in (
            REPO_ROOT / ".claude-plugin" / "plugin.json",
            REPO_ROOT / ".claude-plugin" / "marketplace.json",
            REPO_ROOT / "skills" / "sdr-grader" / "README.md",
            REPO_ROOT / "skills" / "sdr-grader" / "SKILL.md",
            REPO_ROOT
            / "skills"
            / "sdr-grader"
            / "scripts"
            / "query_grade.py",
            REPO_ROOT / "pyproject.toml",
            REPO_ROOT / "README.md",
            REPO_ROOT / "CHANGELOG.md",
            REPO_ROOT / "LICENSE",
        ):
            relative = path.relative_to(REPO_ROOT).as_posix()
            sdist_files[f"{SDIST_ROOT}/{relative}"] = path.read_bytes()
        sdist_files[f"{SDIST_ROOT}/PKG-INFO"] = (
            f"Metadata-Version: 2.4\nName: sdr-grader\nVersion: {metadata_version}\n"
        ).encode()
        if forbidden_member:
            sdist_files[f"{SDIST_ROOT}/{forbidden_member}"] = b"PRIVATE"
        for name, payload in sdist_files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return wheel, sdist


def test_release_verifier_accepts_exact_candidate_and_writes_provenance(
    tmp_path,
):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    wheel, sdist = _write_candidate(dist_dir)
    manifest = tmp_path / "evidence" / "release-artifacts.json"

    result = module.verify_release_artifacts(
        dist_dir,
        source_root=REPO_ROOT,
        expected_version=VERSION,
        source_sha="a" * 40,
        output_path=manifest,
    )

    assert result["source_sha"] == "a" * 40
    assert result["version"] == VERSION
    assert result["inventory"]["wheel"]["file_count"] > 0
    assert result["inventory"]["sdist"]["file_count"] > 0
    assert len(result["inventory"]["wheel"]["tree_sha256"]) == 64
    assert len(result["inventory"]["sdist"]["tree_sha256"]) == 64
    assert result["artifacts"] == [
        {
            "filename": wheel.name,
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "size": wheel.stat().st_size,
        },
        {
            "filename": sdist.name,
            "sha256": hashlib.sha256(sdist.read_bytes()).hexdigest(),
            "size": sdist.stat().st_size,
        },
    ]
    assert json.loads(manifest.read_text(encoding="utf-8")) == result


def test_release_verifier_normalizes_artifact_read_failures(
    tmp_path,
    monkeypatch,
):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    wheel, _sdist = _write_candidate(dist_dir)
    original_open = Path.open

    def failing_open(path, *args, **kwargs):
        if path == wheel:
            raise OSError("private host detail")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)

    with pytest.raises(
        module.VerificationError,
        match=f"could not read candidate artifact: {wheel.name}",
    ):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )


def test_release_verifier_requires_exactly_one_wheel_and_sdist(tmp_path):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    with pytest.raises(module.VerificationError, match="exactly one wheel"):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )

    _write_candidate(dist_dir)
    (dist_dir / "extra.whl").write_bytes(b"unexpected")
    with pytest.raises(module.VerificationError, match="exactly one wheel"):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )


@pytest.mark.parametrize(
    "member",
    [
        ".env",
        "tests/fixtures/private/customer.json",
        "docs/plans/private-review.md",
        "sdr_grader/__pycache__/secret.pyc",
    ],
)
def test_release_verifier_rejects_private_local_cache_and_test_members(
    tmp_path,
    member,
):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _write_candidate(dist_dir, forbidden_member=member)

    with pytest.raises(module.VerificationError, match="forbidden"):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )


def test_release_verifier_rejects_installed_metadata_version_drift(tmp_path):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _write_candidate(dist_dir, metadata_version="9.9.9")

    with pytest.raises(module.VerificationError, match="metadata"):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )


def test_release_verifier_rejects_source_byte_drift(tmp_path):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    wheel, _sdist = _write_candidate(dist_dir)
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(wheel, "a") as archive,
    ):
        archive.writestr(
            "sdr_grader/__init__.py",
            b'__version__ = "9.9.9"\n',
        )

    with pytest.raises(module.VerificationError, match="duplicate|source bytes"):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )

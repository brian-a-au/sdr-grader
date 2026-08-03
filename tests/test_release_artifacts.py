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


def _load_module(*, stub_renderer: bool = True):
    spec = importlib.util.spec_from_file_location(
        "verify_release_artifacts",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if stub_renderer:
        module.render_description = lambda description: "<p>rendered description</p>"
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
    description: str | None = None,
    sdist_description: str | None = None,
) -> tuple[Path, Path]:
    source_files = _source_files(REPO_ROOT)
    description = description if description is not None else (REPO_ROOT / "README.md").read_text()
    sdist_description = description if sdist_description is None else sdist_description

    def metadata(version: str, body: str) -> str:
        return (
            "Metadata-Version: 2.4\n"
            "Name: sdr-grader\n"
            f"Version: {version}\n"
            "Description-Content-Type: text/markdown\n"
            "\n"
            f"{body}"
        )

    wheel = dist_dir / f"sdr_grader-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, payload in source_files.items():
            archive.writestr(name, payload)
        archive.writestr(
            f"{DIST_INFO}/METADATA",
            metadata(metadata_version, description),
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
            REPO_ROOT / "requirements" / "release-validation.in",
            REPO_ROOT / "requirements" / "release-validation.txt",
        ):
            relative = path.relative_to(REPO_ROOT).as_posix()
            sdist_files[f"{SDIST_ROOT}/{relative}"] = path.read_bytes()
        sdist_files[f"{SDIST_ROOT}/PKG-INFO"] = metadata(
            metadata_version,
            sdist_description,
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


def test_release_verifier_requires_source_wheel_and_sdist_descriptions_to_match(tmp_path):
    module = _load_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _write_candidate(dist_dir, sdist_description="# drifted sdist description\n")

    with pytest.raises(module.VerificationError, match="description.*source README|descriptions differ"):
        module.verify_release_artifacts(
            dist_dir,
            source_root=REPO_ROOT,
            expected_version=VERSION,
        )


@pytest.mark.parametrize(
    ("rendered", "message"),
    [
        ('<a href="docs/JSON_OUTPUT.md">JSON</a>', "repository-relative"),
        ('<img src="../private.png">', "repository-relative"),
        (
            '<a href="https://github.com/brian-a-au/sdr-grader/blob/'
            f'v{VERSION}/docs/%2e%2e/README.md">escape</a>',
            "unsafe",
        ),
        (
            '<a href="https://github.com/brian-a-au/sdr-grader/blob/'
            f'v{VERSION}/docs/%252e%252e/README.md">double escape</a>',
            "unsafe",
        ),
        (
            '<a href="https://github.com/brian-a-au/sdr-grader/blob/main/'
            'docs/JSON_OUTPUT.md">mutable docs</a>',
            "immutable",
        ),
        (
            '<a href="https://github.com/brian-a-au/sdr-grader/tree/'
            f'v{VERSION}/README.md">wrong kind</a>',
            "blob",
        ),
    ],
)
def test_rendered_description_rejects_unsafe_or_incorrect_repository_targets(
    rendered,
    message,
):
    module = _load_module()

    with pytest.raises(module.VerificationError, match=message):
        module.validate_rendered_description(
            rendered,
            source_root=REPO_ROOT,
            version=VERSION,
        )


def test_rendered_description_accepts_contained_release_and_main_targets():
    module = _load_module()
    rendered = (
        '<a href="https://github.com/brian-a-au/sdr-grader/blob/'
        f'v{VERSION}/docs/JSON_OUTPUT.md">JSON</a>'
        '<a href="https://github.com/brian-a-au/sdr-grader/tree/'
        f'v{VERSION}/skills/sdr-grader">skill</a>'
        '<a href="https://github.com/brian-a-au/sdr-grader/blob/main/SECURITY.md">security</a>'
        '<img src="https://raw.githubusercontent.com/brian-a-au/sdr-grader/'
        f'v{VERSION}/docs/assets/report-card.png">'
    )

    module.validate_rendered_description(
        rendered,
        source_root=REPO_ROOT,
        version=VERSION,
    )


def test_description_renderer_backend_is_mandatory(monkeypatch):
    module = _load_module(stub_renderer=False)

    def missing_backend(name):
        if name == "readme_renderer.markdown":
            raise ModuleNotFoundError(name)
        return __import__(name)

    monkeypatch.setattr(module.importlib, "import_module", missing_backend)

    with pytest.raises(module.VerificationError, match="readme-renderer.*required"):
        module.render_description("# package")

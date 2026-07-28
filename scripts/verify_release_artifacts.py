#!/usr/bin/env python3
"""Verify release archive identity, inventory, source bytes, and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
VERSION_RE = re.compile(r'^__version__ = "([^"]+)"', re.MULTILINE)
METADATA_VERSION_RE = re.compile(r"^Version:\s*(\S+)\s*$", re.MULTILINE)
ALLOWED_SDIST_TOP_LEVEL = {
    ".claude-plugin",
    ".gitignore",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "SECURITY.md",
    "docs",
    "examples",
    "pyproject.toml",
    "scripts",
    "skills",
    "src",
    "uv.lock",
}


class VerificationError(Exception):
    """A candidate artifact failed a release invariant."""


def verify_release_artifacts(
    dist_dir: Path,
    *,
    source_root: Path = ROOT,
    expected_version: str | None = None,
    source_sha: str | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Verify one wheel and one sdist, returning their digest manifest."""
    dist_dir = Path(dist_dir)
    source_root = Path(source_root)
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise VerificationError(
            f"expected exactly one wheel in {dist_dir}, found {len(wheels)}"
        )
    if len(sdists) != 1:
        raise VerificationError(
            f"expected exactly one sdist in {dist_dir}, found {len(sdists)}"
        )

    version = expected_version or _source_version(source_root)
    wheel = wheels[0]
    sdist = sdists[0]
    expected_wheel = f"sdr_grader-{version}-py3-none-any.whl"
    expected_sdist = f"sdr_grader-{version}.tar.gz"
    if wheel.name != expected_wheel:
        raise VerificationError(
            f"wheel filename identity mismatch: expected {expected_wheel}, "
            f"got {wheel.name}"
        )
    if sdist.name != expected_sdist:
        raise VerificationError(
            f"sdist filename identity mismatch: expected {expected_sdist}, "
            f"got {sdist.name}"
        )

    wheel_members = _read_wheel(wheel)
    sdist_members = _read_sdist(sdist)
    _reject_forbidden_members(wheel_members, sdist_root=None)
    sdist_root = f"sdr_grader-{version}"
    _reject_forbidden_members(sdist_members, sdist_root=sdist_root)
    _verify_wheel(
        wheel_members,
        source_root=source_root,
        version=version,
    )
    _verify_sdist(
        sdist_members,
        source_root=source_root,
        version=version,
    )

    if source_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise VerificationError(
            "source SHA must be a lowercase 40-character Git commit"
        )
    manifest = {
        "schema_version": 1,
        "source_sha": source_sha,
        "version": version,
        "artifacts": [
            _artifact_record(wheel),
            _artifact_record(sdist),
        ],
        "inventory": {
            "wheel": _inventory_record(wheel_members),
            "sdist": _inventory_record(sdist_members),
        },
    }
    if output_path is not None:
        try:
            _write_json_atomically(Path(output_path), manifest)
        except OSError as exc:
            raise VerificationError(
                f"could not write provenance manifest: {exc}"
            ) from exc
    return manifest


def _source_version(source_root: Path) -> str:
    try:
        source = (
            source_root / "src" / "sdr_grader" / "__init__.py"
        ).read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(
            f"could not read package version source: {exc}"
        ) from exc
    match = VERSION_RE.search(source)
    if not match:
        raise VerificationError("package version source has no __version__")
    return match.group(1)


def _read_wheel(path: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = _safe_member_name(info.filename)
                if name in members:
                    raise VerificationError(
                        f"wheel has duplicate archive member: {name}"
                    )
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise VerificationError(
                        f"wheel has forbidden symlink member: {name}"
                    )
                if info.file_size > MAX_MEMBER_BYTES:
                    raise VerificationError(
                        f"wheel member exceeds size limit: {name}"
                    )
                total += info.file_size
                if total > MAX_ARCHIVE_BYTES:
                    raise VerificationError(
                        "wheel expanded content exceeds size limit"
                    )
                members[name] = archive.read(info)
    except (OSError, zipfile.BadZipFile) as exc:
        raise VerificationError(f"could not read wheel: {exc}") from exc
    return members


def _read_sdist(path: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for info in archive.getmembers():
                if info.isdir():
                    continue
                name = _safe_member_name(info.name)
                if name in members:
                    raise VerificationError(
                        f"sdist has duplicate archive member: {name}"
                    )
                if not info.isfile():
                    raise VerificationError(
                        f"sdist has forbidden non-file member: {name}"
                    )
                if info.size > MAX_MEMBER_BYTES:
                    raise VerificationError(
                        f"sdist member exceeds size limit: {name}"
                    )
                total += info.size
                if total > MAX_ARCHIVE_BYTES:
                    raise VerificationError(
                        "sdist expanded content exceeds size limit"
                    )
                extracted = archive.extractfile(info)
                if extracted is None:
                    raise VerificationError(
                        f"could not read sdist member: {name}"
                    )
                members[name] = extracted.read()
    except (OSError, tarfile.TarError) as exc:
        raise VerificationError(f"could not read sdist: {exc}") from exc
    return members


def _safe_member_name(raw_name: str) -> str:
    if "\\" in raw_name:
        raise VerificationError(
            f"archive member uses non-portable separators: {raw_name!r}"
        )
    path = PurePosixPath(raw_name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise VerificationError(
            f"archive member escapes its root: {raw_name!r}"
        )
    return path.as_posix()


def _reject_forbidden_members(
    members: dict[str, bytes],
    *,
    sdist_root: str | None,
) -> None:
    for archive_name in members:
        relative = archive_name
        if sdist_root is not None:
            prefix = f"{sdist_root}/"
            if not archive_name.startswith(prefix):
                raise VerificationError(
                    f"sdist member is outside {sdist_root}: {archive_name}"
                )
            relative = archive_name.removeprefix(prefix)
        path = PurePosixPath(relative)
        lowered_parts = tuple(part.lower() for part in path.parts)
        if (
            sdist_root is not None
            and path.parts
            and path.parts[0] not in ALLOWED_SDIST_TOP_LEVEL
        ):
            raise VerificationError(
                "sdist contains forbidden unapproved top-level member: "
                f"{archive_name}"
            )
        forbidden = (
            not path.parts
            or path.name in {".DS_Store", ".env", ".env.local"}
            or path.suffix.lower() in {".pyc", ".pyo"}
            or any(
                part
                in {
                    ".git",
                    ".venv",
                    ".pytest_cache",
                    ".hypothesis",
                    "__pycache__",
                }
                for part in lowered_parts
            )
            or lowered_parts[:1] == ("tests",)
            or lowered_parts[:2] in {
                ("docs", "plans"),
                ("docs", "specs"),
            }
            or lowered_parts[:3] == ("tests", "fixtures", "private")
        )
        if forbidden:
            raise VerificationError(
                f"archive contains forbidden member: {archive_name}"
            )


def _source_package_files(source_root: Path) -> dict[str, bytes]:
    package_root = source_root / "src" / "sdr_grader"
    if not package_root.is_dir():
        raise VerificationError(
            f"source package directory not found: {package_root}"
        )
    files: dict[str, bytes] = {}
    try:
        for path in package_root.rglob("*"):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".pyo"}
            ):
                continue
            if path.is_symlink():
                raise VerificationError(
                    f"source package contains symlink: {path}"
                )
            files[path.relative_to(source_root / "src").as_posix()] = (
                path.read_bytes()
            )
    except OSError as exc:
        raise VerificationError(
            f"could not read source package inventory: {exc}"
        ) from exc
    return files


def _source_plugin_files(
    source_root: Path,
    *,
    wheel_layout: bool,
) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        for relative in (
            Path(".claude-plugin/plugin.json"),
            Path(".claude-plugin/marketplace.json"),
        ):
            archive_name = relative.as_posix()
            if wheel_layout:
                archive_name = f"sdr_grader/plugin/{archive_name}"
            files[archive_name] = (source_root / relative).read_bytes()
        skill_root = source_root / "skills" / "sdr-grader"
        if not skill_root.is_dir():
            raise VerificationError(
                f"source plugin skill directory not found: {skill_root}"
            )
        for path in skill_root.rglob("*"):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise VerificationError(
                    f"source plugin contains symlink: {path}"
                )
            relative = path.relative_to(source_root).as_posix()
            archive_name = relative
            if wheel_layout:
                archive_name = f"sdr_grader/plugin/{relative}"
            files[archive_name] = path.read_bytes()
    except OSError as exc:
        raise VerificationError(
            f"could not read source plugin inventory: {exc}"
        ) from exc
    return files


def _verify_wheel(
    members: dict[str, bytes],
    *,
    source_root: Path,
    version: str,
) -> None:
    expected = _source_package_files(source_root)
    expected.update(_source_plugin_files(source_root, wheel_layout=True))
    _require_exact_source_bytes(members, expected, archive_name="wheel")
    dist_info = f"sdr_grader-{version}.dist-info"
    metadata_name = f"{dist_info}/METADATA"
    entry_points_name = f"{dist_info}/entry_points.txt"
    _verify_metadata_version(
        _required_member(members, metadata_name, "wheel"),
        version=version,
        archive_name="wheel",
    )
    entry_points = _required_member(
        members,
        entry_points_name,
        "wheel",
    ).decode("utf-8", errors="strict")
    if "sdr-grader = sdr_grader.cli.main:main" not in entry_points:
        raise VerificationError(
            "wheel console entry point does not resolve sdr-grader"
        )
    allowed_prefix = f"{dist_info}/"
    unexpected = sorted(
        name
        for name in members
        if name not in expected and not name.startswith(allowed_prefix)
    )
    if unexpected:
        raise VerificationError(
            f"wheel contains unexpected project members: {unexpected}"
        )
    _verify_plugin_versions(
        members,
        manifest_name=(
            "sdr_grader/plugin/.claude-plugin/plugin.json"
        ),
        marketplace_name=(
            "sdr_grader/plugin/.claude-plugin/marketplace.json"
        ),
        version=version,
        archive_name="wheel",
    )


def _verify_sdist(
    members: dict[str, bytes],
    *,
    source_root: Path,
    version: str,
) -> None:
    root = f"sdr_grader-{version}"
    expected = {
        f"{root}/src/{name}": payload
        for name, payload in _source_package_files(source_root).items()
    }
    expected.update(
        {
            f"{root}/{name}": payload
            for name, payload in _source_plugin_files(
                source_root,
                wheel_layout=False,
            ).items()
        }
    )
    for relative in (
        "pyproject.toml",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
    ):
        try:
            expected[f"{root}/{relative}"] = (
                source_root / relative
            ).read_bytes()
        except OSError as exc:
            raise VerificationError(
                f"could not read required source member {relative}: {exc}"
            ) from exc
    _require_exact_source_bytes(members, expected, archive_name="sdist")
    _verify_metadata_version(
        _required_member(members, f"{root}/PKG-INFO", "sdist"),
        version=version,
        archive_name="sdist",
    )
    _verify_plugin_versions(
        members,
        manifest_name=f"{root}/.claude-plugin/plugin.json",
        marketplace_name=f"{root}/.claude-plugin/marketplace.json",
        version=version,
        archive_name="sdist",
    )


def _require_exact_source_bytes(
    members: dict[str, bytes],
    expected: dict[str, bytes],
    *,
    archive_name: str,
) -> None:
    missing = sorted(name for name in expected if name not in members)
    if missing:
        raise VerificationError(
            f"{archive_name} is missing required source members: {missing}"
        )
    drifted = sorted(
        name
        for name, payload in expected.items()
        if members[name] != payload
    )
    if drifted:
        raise VerificationError(
            f"{archive_name} source bytes differ from candidate: {drifted}"
        )


def _required_member(
    members: dict[str, bytes],
    name: str,
    archive_name: str,
) -> bytes:
    try:
        return members[name]
    except KeyError as exc:
        raise VerificationError(
            f"{archive_name} is missing required member: {name}"
        ) from exc


def _verify_metadata_version(
    payload: bytes,
    *,
    version: str,
    archive_name: str,
) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerificationError(
            f"{archive_name} metadata is not UTF-8"
        ) from exc
    match = METADATA_VERSION_RE.search(text)
    if not match or match.group(1) != version:
        observed = match.group(1) if match else None
        raise VerificationError(
            f"{archive_name} metadata version mismatch: "
            f"expected {version}, got {observed!r}"
        )


def _verify_plugin_versions(
    members: dict[str, bytes],
    *,
    manifest_name: str,
    marketplace_name: str,
    version: str,
    archive_name: str,
) -> None:
    try:
        manifest = json.loads(
            _required_member(
                members,
                manifest_name,
                archive_name,
            )
        )
        marketplace = json.loads(
            _required_member(
                members,
                marketplace_name,
                archive_name,
            )
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(
            f"{archive_name} plugin metadata is invalid JSON"
        ) from exc
    plugins = marketplace.get("plugins") if isinstance(marketplace, dict) else None
    entry = next(
        (
            candidate
            for candidate in plugins or []
            if isinstance(candidate, dict)
            and candidate.get("name") == "sdr-grader"
        ),
        {},
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != version
        or entry.get("version") != version
    ):
        raise VerificationError(
            f"{archive_name} plugin metadata version mismatch"
        )


def _artifact_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    try:
        before = path.stat()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
    except OSError as exc:
        raise VerificationError(
            f"could not read candidate artifact: {path.name}"
        ) from exc
    if (before.st_size, before.st_mtime_ns) != (
        after.st_size,
        after.st_mtime_ns,
    ):
        raise VerificationError(
            f"candidate artifact changed during verification: {path.name}"
        )
    return {
        "filename": path.name,
        "sha256": digest.hexdigest(),
        "size": after.st_size,
    }


def _inventory_record(members: dict[str, bytes]) -> dict[str, Any]:
    files = [
        {
            "path": name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
        for name, payload in sorted(members.items())
    ]
    serialized = json.dumps(
        files,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "file_count": len(files),
        "tree_sha256": hashlib.sha256(serialized).hexdigest(),
        "files": files,
    }


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--expected-version")
    parser.add_argument("--source-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = verify_release_artifacts(
            args.dist_dir,
            source_root=args.source_root,
            expected_version=args.expected_version,
            source_sha=args.source_sha,
            output_path=args.output,
        )
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "release artifacts verified: "
        + ", ".join(
            f"{entry['filename']} sha256:{entry['sha256']}"
            for entry in manifest["artifacts"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Safe output-path planning and staged publication for CLI artifacts."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

MAX_DERIVED_LEAF_BYTES = 120
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SEPARATOR_RE = re.compile(r"[-_.]{2,}")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class OutputPathError(ValueError):
    """An output destination is unsafe or collides with another path."""


class OutputPublishError(OSError):
    """A staged output set could not be published."""


def portable_leaf(
    prefix: str,
    identity: object,
    suffix: str,
    *,
    max_bytes: int = MAX_DERIVED_LEAF_BYTES,
) -> str:
    """Build one bounded ASCII filename leaf from an untrusted identity."""
    source = str(identity)
    normalized = unicodedata.normalize("NFKC", source)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    token = _SAFE_TOKEN_RE.sub("-", ascii_value)
    token = _SEPARATOR_RE.sub("-", token).strip(" .-_")
    changed = token != source
    if not token:
        token = "instance"
        changed = True
    if token.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        token = f"id-{token}"
        changed = True

    available = max_bytes - len(prefix.encode("ascii")) - len(suffix.encode("ascii"))
    if available < 18:
        raise ValueError("derived filename budget is too small")
    encoded = token.encode("ascii")
    if changed or len(encoded) > available:
        digest = hashlib.sha256(source.encode("utf-8", errors="surrogatepass")).hexdigest()[:12]
        stem_budget = available - len(digest) - 1
        token = f"{encoded[:stem_budget].decode('ascii').rstrip(' .-_') or 'instance'}-{digest}"

    leaf = f"{prefix}{token}{suffix}"
    if (
        Path(leaf).name != leaf
        or leaf in {".", ".."}
        or len(leaf.encode("ascii")) > max_bytes
    ):
        raise OutputPathError("could not derive a portable output filename")
    return leaf


def validate_output_paths(
    destinations: Iterable[Path],
    *,
    read_paths: Iterable[Path] = (),
) -> tuple[Path, ...]:
    """Validate output targets and reject resolved-identity collisions."""
    planned = tuple(Path(path) for path in destinations)
    identities: dict[Path, Path] = {}
    for path in planned:
        try:
            if path.is_symlink():
                raise OutputPathError("output target must not be a symlink")
            if path.exists() and not path.is_file():
                raise OutputPathError("output target must be a regular file")
            identity = path.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise OutputPathError("could not inspect an output target") from exc
        previous = identities.get(identity)
        if previous is not None:
            raise OutputPathError("output destinations resolve to the same file")
        identities[identity] = path

    for read_path in (Path(path) for path in read_paths):
        try:
            read_identity = read_path.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise OutputPathError("could not inspect an input path") from exc
        if read_identity in identities:
            raise OutputPathError("output destination collides with an input path")
    return planned


def publish_text_artifacts(
    artifacts: Mapping[Path, str],
    *,
    read_paths: Iterable[Path] = (),
) -> None:
    """Stage every text artifact beside its destination, then publish them."""
    destinations = validate_output_paths(artifacts, read_paths=read_paths)
    staged: dict[Path, Path] = {}
    try:
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage = _stage_path(destination)
            _clean_stale_stage(stage)
            _write_stage(stage, artifacts[destination])
            staged[destination] = stage
    except (OSError, UnicodeError) as exc:
        _cleanup_stages(staged.values())
        raise OutputPublishError("could not stage the complete output set") from exc

    try:
        for destination in destinations:
            os.replace(staged[destination], destination)
    except OSError as exc:
        _cleanup_stages(staged.values())
        raise OutputPublishError(
            "could not publish the complete output set; no success was reported"
        ) from exc


def _stage_path(destination: Path) -> Path:
    identity = str(destination.resolve(strict=False)).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:16]
    return destination.parent / f".sdr-grader-{digest}.stage"


def _clean_stale_stage(stage: Path) -> None:
    if stage.is_symlink():
        raise OSError("staging path must not be a symlink")
    if stage.exists():
        if not stage.is_file():
            raise OSError("staging path must be a regular file")
        stage.unlink()


def _write_stage(stage: Path, content: str) -> None:
    descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        stage.unlink(missing_ok=True)
        raise


def _cleanup_stages(stages: Iterable[Path]) -> None:
    for stage in stages:
        try:
            if stage.is_file() and not stage.is_symlink():
                stage.unlink()
        except OSError:
            pass

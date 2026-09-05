#!/usr/bin/env python3
"""Verify candidate README links and published PyPI identity with bounded I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlparse

PROJECT = "sdr-grader"
REPOSITORY_OWNER = "brian-a-au"
REPOSITORY_NAME = "sdr-grader"
MAX_ATTEMPTS = 3
PYPI_PROPAGATION_ATTEMPTS = 16
PYPI_PROPAGATION_TIMEOUT_SECONDS = 300.0
MAX_RETRY_DELAY_SECONDS = 30.0
MAX_REDIRECTS = 5
REQUEST_TIMEOUT_SECONDS = 15.0
TOTAL_TIMEOUT_SECONDS = 60.0
MAX_LINK_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TRANSIENT_HTTP_STATUSES = {429, *range(500, 600)}
RELEASE_PINNED_ROOTS = {"docs", "examples", "skills", "src", "tests"}
PREREQUISITE_LINKS = {
    "https://github.com/brian-a-au/cja_auto_sdr#install-from-pypi-recommended",
    "https://github.com/brian-a-au/cja_auto_sdr#3-configure-credentials",
    "https://github.com/brian-a-au/aa_auto_sdr#install-from-pypi-recommended",
    "https://github.com/brian-a-au/aa_auto_sdr#3-configure-credentials-adobe-analytics-api-20-oauth-server-to-server",
}


class VerificationError(Exception):
    """Base class for a release-verification failure."""


class PolicyError(VerificationError):
    """A URL, redirect, response, or artifact violated the bounded policy."""


class ContentError(VerificationError):
    """Published content differs from the immutable candidate contract."""


class TransientExhaustedError(VerificationError):
    """All bounded attempts failed for a retryable transport condition."""


class _TransientAttempt(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


class BoundedClient:
    """Unauthenticated HTTPS client with explicit redirect and retry bounds."""

    def __init__(self, *, opener=None, sleep: Callable[[float], None] = time.sleep):
        self._opener = opener or urllib.request.build_opener(_NoRedirect())
        self._sleep = sleep

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int = MAX_LINK_BYTES,
        retry_not_found: bool = False,
    ) -> bytes:
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise PolicyError("response byte bound must be a positive integer")
        total_timeout = (
            PYPI_PROPAGATION_TIMEOUT_SECONDS if retry_not_found else TOTAL_TIMEOUT_SECONDS
        )
        deadline = time.monotonic() + total_timeout
        last_error = "unknown transient failure"
        max_attempts = PYPI_PROPAGATION_ATTEMPTS if retry_not_found else MAX_ATTEMPTS
        for attempt in range(max_attempts):
            try:
                return self._fetch_once(
                    url,
                    max_bytes=max_bytes,
                    deadline=deadline,
                    retry_not_found=retry_not_found,
                )
            except _TransientAttempt as exc:
                last_error = str(exc)
                if attempt + 1 == max_attempts:
                    break
                delay = min(
                    2**attempt, MAX_RETRY_DELAY_SECONDS, max(0.0, deadline - time.monotonic())
                )
                if delay <= 0:
                    break
                self._sleep(delay)
        raise TransientExhaustedError(
            f"transient request failure exhausted {max_attempts} attempts: {last_error}"
        )

    def _fetch_once(
        self,
        url: str,
        *,
        max_bytes: int,
        deadline: float,
        retry_not_found: bool,
    ) -> bytes:
        current = _validated_url(url)
        for hop in range(MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _TransientAttempt("bounded request deadline expired")
            timeout = min(REQUEST_TIMEOUT_SECONDS, remaining)
            request_url, _fragment = urldefrag(current)
            request = urllib.request.Request(
                request_url,
                headers={
                    "Accept": "*/*",
                    "User-Agent": "sdr-grader-release-verifier/1",
                },
                method="GET",
            )
            try:
                response = self._opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as exc:
                if exc.code in REDIRECT_STATUSES:
                    response = exc
                elif exc.code in TRANSIENT_HTTP_STATUSES or (retry_not_found and exc.code == 404):
                    raise _TransientAttempt(f"HTTP {exc.code}") from exc
                else:
                    raise ContentError(f"persistent HTTP {exc.code} for {request_url}") from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                raise _TransientAttempt(type(exc).__name__) from exc

            try:
                with response:
                    status = int(getattr(response, "status", getattr(response, "code", 200)))
                    if status in REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            raise PolicyError("redirect response omitted Location")
                        if hop == MAX_REDIRECTS:
                            raise PolicyError("redirect hop limit exceeded")
                        current = _validated_url(urljoin(request_url, location))
                        continue
                    if status in TRANSIENT_HTTP_STATUSES or (retry_not_found and status == 404):
                        raise _TransientAttempt(f"HTTP {status}")
                    if not 200 <= status < 300:
                        raise ContentError(f"persistent HTTP {status} for {request_url}")
                    payload = response.read(max_bytes + 1)
                    if len(payload) > max_bytes:
                        raise PolicyError(f"response byte limit exceeded for {request_url}")
                    return payload
            except (VerificationError, _TransientAttempt):
                raise
            except (TimeoutError, ConnectionError, OSError) as exc:
                raise _TransientAttempt(type(exc).__name__) from exc
        raise PolicyError("redirect hop limit exceeded")


def verify_candidate(
    dist_dir: Path,
    evidence_path: Path,
    *,
    version: str,
    source_sha: str | None = None,
) -> dict[str, Any]:
    """Verify downloaded distributions against their retained digest evidence."""
    _description, artifacts = _candidate_context(
        dist_dir,
        evidence_path,
        version=version,
        source_sha=source_sha,
    )
    return {
        "mode": "candidate",
        "version": version,
        "artifact_digests": {name: record["sha256"] for name, record in artifacts.items()},
    }


def verify_prepublication(
    dist_dir: Path,
    evidence_path: Path,
    *,
    version: str,
    fetch: Callable[..., bytes] | None = None,
) -> dict[str, Any]:
    """Verify exact candidate metadata and live tagged/allowlisted README links."""
    description, artifacts = _candidate_context(dist_dir, evidence_path, version=version)
    fetcher = fetch or BoundedClient().fetch
    links_checked = _verify_live_links(description, version=version, fetcher=fetcher)
    return {
        "mode": "prepublication",
        "version": version,
        "artifact_digests": {name: record["sha256"] for name, record in artifacts.items()},
        "links_checked": links_checked,
    }


def verify_postpublication(
    dist_dir: Path,
    evidence_path: Path,
    *,
    version: str,
    fetch: Callable[..., bytes] | None = None,
) -> dict[str, Any]:
    """Verify PyPI description and bytes equal the candidate, then recheck links."""
    description, artifacts = _candidate_context(dist_dir, evidence_path, version=version)
    fetcher = fetch or BoundedClient().fetch
    metadata_url = f"https://pypi.org/pypi/{PROJECT}/{version}/json"
    try:
        metadata = json.loads(
            fetcher(
                metadata_url,
                max_bytes=MAX_JSON_BYTES,
                retry_not_found=True,
            )
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ContentError("PyPI metadata is not valid bounded JSON") from exc
    if not isinstance(metadata, dict):
        raise ContentError("PyPI metadata must be a JSON object")
    info = metadata.get("info")
    if not isinstance(info, dict):
        raise ContentError("PyPI metadata has no info object")
    if info.get("description") != description:
        raise ContentError("PyPI description differs from candidate metadata")
    content_type = info.get("description_content_type")
    if (
        not isinstance(content_type, str)
        or content_type.split(";", 1)[0].strip() != "text/markdown"
    ):
        raise ContentError("PyPI description content type is not text/markdown")

    remote_entries = metadata.get("urls")
    if not isinstance(remote_entries, list):
        raise ContentError("PyPI metadata has no artifact URL list")
    remote: dict[str, dict[str, Any]] = {}
    for entry in remote_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise ContentError("PyPI artifact metadata is malformed")
        filename = entry["filename"]
        if filename in remote:
            raise ContentError(f"PyPI artifact metadata duplicates {filename}")
        remote[filename] = entry
    if set(remote) != set(artifacts):
        raise ContentError("PyPI artifact inventory differs from candidate evidence")
    for filename, expected in artifacts.items():
        entry = remote[filename]
        digests = entry.get("digests")
        url = entry.get("url")
        if (
            not isinstance(digests, dict)
            or digests.get("sha256") != expected["sha256"]
            or entry.get("size") != expected["size"]
            or not isinstance(url, str)
        ):
            raise ContentError(f"PyPI metadata differs for {filename}")
        _validate_file_url(url)
        payload = fetcher(url, max_bytes=MAX_ARTIFACT_BYTES)
        if (
            len(payload) != expected["size"]
            or hashlib.sha256(payload).hexdigest() != expected["sha256"]
        ):
            raise ContentError(f"PyPI bytes differ for {filename}")

    links_checked = _verify_live_links(description, version=version, fetcher=fetcher)
    return {
        "mode": "postpublication",
        "version": version,
        "artifact_digests": {name: record["sha256"] for name, record in artifacts.items()},
        "links_checked": links_checked,
    }


def _candidate_context(
    dist_dir: Path,
    evidence_path: Path,
    *,
    version: str,
    source_sha: str | None = None,
) -> tuple[str, dict[str, dict[str, Any]]]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise PolicyError("version must be exactly X.Y.Z")
    dist_dir = Path(dist_dir)
    wheel = _only(dist_dir.glob("*.whl"), "wheel")
    sdist = _only(dist_dir.glob("*.tar.gz"), "sdist")
    expected_names = {
        f"sdr_grader-{version}-py3-none-any.whl",
        f"sdr_grader-{version}.tar.gz",
    }
    if {wheel.name, sdist.name} != expected_names:
        raise ContentError("candidate filenames do not match requested version")
    wheel_description = _wheel_description(wheel, version=version)
    sdist_description = _sdist_description(sdist, version=version)
    if wheel_description != sdist_description:
        raise ContentError("wheel and sdist descriptions differ")
    try:
        evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentError("candidate evidence is unreadable") from exc
    if not isinstance(evidence, dict) or evidence.get("version") != version:
        raise ContentError("candidate evidence version differs")
    if source_sha is not None:
        if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
            raise PolicyError("source commit must be a full lowercase SHA")
        if evidence.get("source_sha") != source_sha:
            raise ContentError("candidate evidence source commit differs")
    entries = evidence.get("artifacts")
    if not isinstance(entries, list):
        raise ContentError("candidate evidence has no artifact list")
    artifacts: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise ContentError("candidate evidence artifact is malformed")
        artifacts[entry["filename"]] = entry
    if set(artifacts) != expected_names:
        raise ContentError("candidate evidence inventory differs")
    for path in (wheel, sdist):
        record = artifacts[path.name]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if record.get("size") != path.stat().st_size or record.get("sha256") != digest:
            raise ContentError(f"candidate evidence digest differs for {path.name}")
    return wheel_description, artifacts


def _only(paths, kind: str) -> Path:
    matches = sorted(paths)
    if len(matches) != 1:
        raise ContentError(f"expected exactly one candidate {kind}")
    return matches[0]


def _wheel_description(path: Path, *, version: str) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ContentError("wheel must contain exactly one METADATA file")
            return _metadata_description(archive.read(names[0]), version=version, kind="wheel")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ContentError("candidate wheel metadata is unreadable") from exc


def _sdist_description(path: Path, *, version: str) -> str:
    expected = f"sdr_grader-{version}/PKG-INFO"
    try:
        with tarfile.open(path, "r:gz") as archive:
            member = archive.getmember(expected)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ContentError("sdist PKG-INFO is not a regular file")
            return _metadata_description(extracted.read(), version=version, kind="sdist")
    except (OSError, tarfile.TarError, KeyError) as exc:
        raise ContentError("candidate sdist metadata is unreadable") from exc


def _metadata_description(payload: bytes, *, version: str, kind: str) -> str:
    separator = b"\r\n\r\n" if b"\r\n\r\n" in payload else b"\n\n"
    header, found, body = payload.partition(separator)
    if not found:
        raise ContentError(f"{kind} metadata description is missing")
    try:
        header_text = header.decode("utf-8")
        description = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContentError(f"{kind} metadata is not UTF-8") from exc
    version_match = re.search(r"^Version:\s*(\S+)\s*$", header_text, re.MULTILINE)
    type_match = re.search(r"^Description-Content-Type:\s*([^;\s]+)", header_text, re.MULTILINE)
    if not version_match or version_match.group(1) != version:
        raise ContentError(f"{kind} metadata version differs")
    if not type_match or type_match.group(1) != "text/markdown":
        raise ContentError(f"{kind} description content type is not text/markdown")
    if not description:
        raise ContentError(f"{kind} metadata description is missing")
    return description


def _markdown_targets(description: str) -> list[str]:
    return [
        match.group(1).split(maxsplit=1)[0].strip("<>")
        for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", description)
    ]


def _live_links(description: str, *, version: str) -> list[str]:
    selected: list[str] = []
    for target in _markdown_targets(description):
        parsed = urlparse(target)
        if _is_same_repository(parsed):
            _validate_same_repository_link(parsed, version=version)
            selected.append(target)
        elif target in PREREQUISITE_LINKS:
            _validated_url(target)
            selected.append(target)
    return list(dict.fromkeys(selected))


def _verify_live_links(
    description: str,
    *,
    version: str,
    fetcher: Callable[..., bytes],
) -> int:
    links = _live_links(description, version=version)
    urls = [_tag_url(version), *links]
    for url in urls:
        fetcher(url, max_bytes=MAX_LINK_BYTES)
    return len(urls)


def _tag_url(version: str) -> str:
    return f"https://github.com/{REPOSITORY_OWNER}/{REPOSITORY_NAME}/tree/v{version}"


def _is_same_repository(parsed) -> bool:
    host = parsed.hostname
    parts = [part for part in _decoded_path(parsed.path).split("/") if part]
    return host in {
        "github.com",
        "raw.githubusercontent.com",
        "raw.githack.com",
        "rawcdn.githack.com",
    } and parts[:2] == [REPOSITORY_OWNER, REPOSITORY_NAME]


def _validate_same_repository_link(parsed, *, version: str) -> None:
    _validated_url(parsed.geturl())
    path = _decoded_path(parsed.path)
    parts = [part for part in path.split("/") if part]
    expected_ref = f"v{version}"
    if parsed.hostname == "github.com" and len(parts) >= 4 and parts[2] in {"blob", "tree"}:
        ref = parts[3]
        repo_path = parts[4:]
        if not repo_path or (repo_path and repo_path[0] in RELEASE_PINNED_ROOTS):
            if ref != expected_ref:
                raise PolicyError(f"same-repository release ref must be {expected_ref}")
        elif ref not in {"main", expected_ref}:
            raise PolicyError("same-repository link has unsupported ref")
    elif parsed.hostname != "github.com":
        if len(parts) < 4 or parts[2] != expected_ref:
            raise PolicyError(f"same-repository release ref must be {expected_ref}")


def _validated_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise PolicyError("live URL must use HTTPS")
    try:
        port = parsed.port
    except ValueError as exc:
        raise PolicyError("live URL contains an invalid port") from exc
    if parsed.username or parsed.password or port not in {None, 443}:
        raise PolicyError("live URL contains forbidden authority fields")
    if parsed.query:
        raise PolicyError("live URL query is not allowlisted")
    host = parsed.hostname
    path = _decoded_path(parsed.path)
    parts = [part for part in path.split("/") if part]
    allowed = False
    if host == "github.com":
        repo = tuple(parts[:2])
        allowed_repositories = {
            (REPOSITORY_OWNER, REPOSITORY_NAME),
            (REPOSITORY_OWNER, "cja_auto_sdr"),
            (REPOSITORY_OWNER, "aa_auto_sdr"),
        }
        prerequisite_repositories = {
            (REPOSITORY_OWNER, "cja_auto_sdr"),
            (REPOSITORY_OWNER, "aa_auto_sdr"),
        }
        allowed = repo in allowed_repositories
        if repo in prerequisite_repositories and len(parts) != 2:
            allowed = False
    elif host in {"raw.githubusercontent.com", "raw.githack.com", "rawcdn.githack.com"}:
        allowed = parts[:2] == [REPOSITORY_OWNER, REPOSITORY_NAME]
    elif host == "pypi.org":
        allowed = (
            len(parts) == 4 and parts[0] == "pypi" and parts[1] == PROJECT and parts[3] == "json"
        )
    elif host == "files.pythonhosted.org":
        allowed = bool(parts) and parts[0] == "packages"
    if not allowed:
        raise PolicyError(f"live URL host/path is not allowlisted: {host}{path}")
    return parsed.geturl()


def _validate_file_url(url: str) -> None:
    parsed = urlparse(_validated_url(url))
    if parsed.hostname != "files.pythonhosted.org" or not parsed.path.startswith("/packages/"):
        raise PolicyError("PyPI artifact URL is not on the files allowlist")


def _decoded_path(path: str) -> str:
    decoded = path
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if re.search(r"%[0-9a-fA-F]{2}", decoded) or "\\" in decoded or "\x00" in decoded:
        raise PolicyError("live URL has unsafe path encoding")
    pure = PurePosixPath(decoded)
    if any(part in {".", ".."} for part in pure.parts):
        raise PolicyError("live URL has unsafe path traversal")
    return decoded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("candidate", "prepublication", "postpublication"):
        command = subparsers.add_parser(mode)
        command.add_argument("--dist-dir", type=Path, required=True)
        command.add_argument("--evidence", type=Path, required=True)
        command.add_argument("--version", required=True)
        if mode == "candidate":
            command.add_argument("--source-sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    verifier = {
        "candidate": verify_candidate,
        "prepublication": verify_prepublication,
        "postpublication": verify_postpublication,
    }[args.mode]
    try:
        kwargs = {"version": args.version}
        if args.mode == "candidate":
            kwargs["source_sha"] = args.source_sha
        result = verifier(args.dist_dir, args.evidence, **kwargs)
    except TransientExhaustedError as exc:
        print(f"transient-exhausted: {exc}", file=sys.stderr)
        return 75
    except VerificationError as exc:
        print(f"verification-failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

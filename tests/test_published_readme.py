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
SCRIPT = REPO_ROOT / "scripts" / "verify_published_readme.py"
VERSION = "1.2.3"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_published_readme", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifacts(tmp_path: Path, description: str) -> tuple[Path, Path, Path]:
    dist = tmp_path / "dist"
    dist.mkdir()
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: sdr-grader\n"
        f"Version: {VERSION}\n"
        "Description-Content-Type: text/markdown\n\n"
        f"{description}"
    ).encode()
    wheel = dist / f"sdr_grader-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"sdr_grader-{VERSION}.dist-info/METADATA", metadata)
    sdist = dist / f"sdr_grader-{VERSION}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo(f"sdr_grader-{VERSION}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))
    evidence = tmp_path / "release-artifacts.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": VERSION,
                "artifacts": [
                    {
                        "filename": path.name,
                        "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for path in (wheel, sdist)
                ],
            }
        ),
        encoding="utf-8",
    )
    return dist, wheel, evidence


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, *, status: int = 200, headers=None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_prepublication_checks_candidate_digests_and_exact_tag_links(tmp_path):
    module = _load_module()
    description = (
        "[docs](https://github.com/brian-a-au/sdr-grader/blob/v1.2.3/README.md)\n"
        "[install](https://github.com/brian-a-au/cja_auto_sdr#install-from-pypi-recommended)\n"
    )
    dist, _wheel, evidence = _artifacts(tmp_path, description)
    seen = []

    module.verify_prepublication(
        dist,
        evidence,
        version=VERSION,
        fetch=lambda url, **_kwargs: seen.append(url) or b"ok",
    )

    assert "https://github.com/brian-a-au/sdr-grader/tree/v1.2.3" in seen
    assert "https://github.com/brian-a-au/sdr-grader/blob/v1.2.3/README.md" in seen
    assert "https://github.com/brian-a-au/cja_auto_sdr#install-from-pypi-recommended" in seen


def test_prepublication_rejects_non_tagged_release_link(tmp_path):
    module = _load_module()
    dist, _wheel, evidence = _artifacts(
        tmp_path,
        "[docs](https://github.com/brian-a-au/sdr-grader/blob/v9.9.9/docs/JSON_OUTPUT.md)\n",
    )

    with pytest.raises(module.PolicyError, match="release ref"):
        module.verify_prepublication(
            dist,
            evidence,
            version=VERSION,
            fetch=lambda *_args, **_kwargs: b"ok",
        )


def test_postpublication_requires_pypi_description_and_byte_digest_equality(tmp_path):
    module = _load_module()
    description = "[docs](https://github.com/brian-a-au/sdr-grader/blob/v1.2.3/README.md)\n"
    dist, wheel, evidence = _artifacts(tmp_path, description)
    wheel_url = f"https://files.pythonhosted.org/packages/{wheel.name}"
    sdist = next(dist.glob("*.tar.gz"))
    sdist_url = f"https://files.pythonhosted.org/packages/{sdist.name}"
    pypi = {
        "info": {
            "description": description,
            "description_content_type": "text/markdown",
        },
        "urls": [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "digests": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                "url": url,
            }
            for path, url in ((wheel, wheel_url), (sdist, sdist_url))
        ],
    }
    payloads = {
        f"https://pypi.org/pypi/sdr-grader/{VERSION}/json": json.dumps(pypi).encode(),
        wheel_url: wheel.read_bytes(),
        sdist_url: sdist.read_bytes(),
        "https://github.com/brian-a-au/sdr-grader/tree/v1.2.3": b"tag",
        "https://github.com/brian-a-au/sdr-grader/blob/v1.2.3/README.md": b"readme",
    }

    module.verify_postpublication(
        dist,
        evidence,
        version=VERSION,
        fetch=lambda url, **_kwargs: payloads[url],
    )

    pypi["info"]["description"] += "drift"
    payloads[f"https://pypi.org/pypi/sdr-grader/{VERSION}/json"] = json.dumps(pypi).encode()
    with pytest.raises(module.ContentError, match="description"):
        module.verify_postpublication(
            dist,
            evidence,
            version=VERSION,
            fetch=lambda url, **_kwargs: payloads[url],
        )


def test_bounded_client_disables_auth_cookies_and_validates_redirects():
    module = _load_module()
    opener = _Opener(
        [
            _Response(b"", status=302, headers={"Location": "/brian-a-au/sdr-grader/tree/v1.2.3"}),
            _Response(b"ok"),
        ]
    )
    client = module.BoundedClient(opener=opener, sleep=lambda _delay: None)

    assert client.fetch("https://github.com/brian-a-au/sdr-grader") == b"ok"
    assert len(opener.requests) == 2
    for request, timeout in opener.requests:
        headers = {key.lower(): value for key, value in request.header_items()}
        assert "authorization" not in headers
        assert "cookie" not in headers
        assert timeout <= module.REQUEST_TIMEOUT_SECONDS

    unsafe = _Opener(
        [_Response(b"", status=302, headers={"Location": "https://evil.example/file"})]
    )
    with pytest.raises(module.PolicyError, match="host"):
        module.BoundedClient(opener=unsafe, sleep=lambda _delay: None).fetch(
            "https://github.com/brian-a-au/sdr-grader"
        )


def test_bounded_client_rejects_hops_oversize_and_classifies_transient_exhaustion():
    module = _load_module()
    looping = _Opener(
        [
            _Response(b"", status=302, headers={"Location": "/brian-a-au/sdr-grader"})
            for _ in range(module.MAX_REDIRECTS + 1)
        ]
    )
    with pytest.raises(module.PolicyError, match="redirect"):
        module.BoundedClient(opener=looping, sleep=lambda _delay: None).fetch(
            "https://github.com/brian-a-au/sdr-grader"
        )

    oversized = _Opener([_Response(b"12345")])
    with pytest.raises(module.PolicyError, match="response byte"):
        module.BoundedClient(opener=oversized, sleep=lambda _delay: None).fetch(
            "https://github.com/brian-a-au/sdr-grader", max_bytes=4
        )

    transient = _Opener([OSError("temporary") for _ in range(module.MAX_ATTEMPTS)])
    with pytest.raises(module.TransientExhaustedError, match="transient"):
        module.BoundedClient(opener=transient, sleep=lambda _delay: None).fetch(
            "https://github.com/brian-a-au/sdr-grader"
        )

#!/usr/bin/env python3
"""Nonpublishing hosted transport fixtures for the actual release job graph.

This command cannot run in tag releases. Artifact creation, manifest validation,
attestation verification, smoke tests, uv execution and terminal job API checks
remain the production implementations. Only endpoint responses/index visibility
and explicitly named negative scenarios are fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from install_public_release import install_public_release, run_process
from verify_github_release_assets import verify_release_assets
from verify_published_readme import (
    _candidate_context,
    _live_links,
    _tag_url,
    verify_candidate,
    verify_postpublication,
    verify_prepublication,
)

SCENARIOS = {'success', 'fail-once', 'fail-later', 'skip', 'cancel', 'discovery',
             'exhausted', 'mismatch', 'source-mismatch'}


def guard(*, fixture_required=False):
    harness = os.environ.get('HARNESS_MODE') == 'true'
    event = os.environ.get('GITHUB_EVENT_NAME')
    ref = os.environ.get('GITHUB_REF', '')
    if harness:
        if event != 'workflow_dispatch' or not ref.startswith('refs/heads/'):
            raise ValueError('fixtures require a non-tag workflow dispatch')
        caller = os.environ.get('CALLER_WORKFLOW', os.environ.get('GITHUB_WORKFLOW_REF', ''))
        expected = os.environ['GITHUB_REPOSITORY'] + '/.github/workflows/release.yml@' + ref
        if caller != expected:
            raise ValueError('fixture caller is not the fixed release workflow')
        if os.environ.get('HARNESS_SCENARIO', 'success') not in SCENARIOS:
            raise ValueError('unknown harness scenario')
    elif fixture_required or event != 'push' or not ref.startswith('refs/tags/v'):
        raise ValueError('production requires a tag push; fixtures cannot be activated')


class FixtureTransport:
    def __init__(self, dist_dir: Path, evidence: Path, version: str, *, mismatch=False):
        self.dist_dir, self.evidence, self.version = dist_dir, evidence, version
        description, records = _candidate_context(dist_dir, evidence, version=version)
        self.urls = []
        self.payloads = {
            _tag_url(version): b'<html>synthetic frozen tag fixture</html>',
            **{url: b'<html>synthetic README link fixture</html>'
               for url in _live_links(description, version=version)},
        }
        entries = []
        for filename, record in records.items():
            url = 'https://files.pythonhosted.org/packages/fixture/' + filename
            self.payloads[url] = (dist_dir / filename).read_bytes()
            entries.append({'filename': filename, 'size': record['size'],
                            'digests': {'sha256': record['sha256']}, 'url': url})
        if mismatch:
            entries[0]['digests']['sha256'] = '0' * 64
        self.payloads[f'https://pypi.org/pypi/sdr-grader/{version}/json'] = json.dumps({
            'info': {'description': description, 'description_content_type': 'text/markdown'},
            'urls': entries,
        }).encode()

    def fetch(self, url, *, max_bytes, retry_not_found=False):
        del retry_not_found
        self.urls.append(url)
        if url not in self.payloads:
            raise ValueError('unexpected fixture endpoint: ' + url)
        payload = self.payloads[url]
        if len(payload) > max_bytes:
            raise ValueError('fixture exceeds production response byte bound')
        return payload

    def inventory(self, *, source_mismatch=False):
        expected_sha = '0' * 40 if source_mismatch else os.environ['GITHUB_SHA']
        verify_candidate(self.dist_dir, self.evidence, version=self.version, source_sha=expected_sha)
        paths = [*self.dist_dir.iterdir(), self.evidence]
        release = {'tagName': 'v' + self.version, 'isDraft': False, 'assets': [
            {'name': path.name, 'size': path.stat().st_size,
             'digest': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in paths]}
        verify_release_assets(release=release, evidence_path=self.evidence,
                              dist_dir=self.dist_dir, expected_tag='v' + self.version,
                              release_state='published')
        return release


def install_fixture(transport, *, python, scenario, output):
    """Serve a real local simple index to pinned uv, retaining its real diagnostics."""
    state = {'attempt': 0, 'requests': []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._respond(send_body=True)

        def do_HEAD(self):
            self._respond(send_body=False)

        def _respond(self, *, send_body):
            path = unquote(urlparse(self.path).path)
            state['requests'].append(path)
            if path == '/simple/sdr-grader/':
                hidden = scenario == 'exhausted' or (scenario == 'discovery' and state['attempt'] == 1)
                if hidden:
                    # A known other version exercises exact-version absence,
                    # instead of the distinct unknown-project diagnostic.
                    body = b'<a href="/files/sdr_grader-0.0.0-py3-none-any.whl">other version</a>'
                else:
                    body = '\n'.join(
                        f'<a href="/files/{p.name}#sha256={hashlib.sha256(p.read_bytes()).hexdigest()}">{p.name}</a>'
                        for p in transport.dist_dir.iterdir()).encode()
            elif path.startswith('/files/') and Path(path).name in {
                    p.name for p in transport.dist_dir.iterdir()}:
                body = (transport.dist_dir / Path(path).name).read_bytes()
            elif re.fullmatch(r'/simple/[a-z0-9-]+/', path):
                # Dependencies use the real public index; candidate identity
                # always comes exclusively from the retained fixture bytes.
                request = urllib.request.Request('https://pypi.org' + path,
                                                 headers={'Accept': 'text/html'})
                with urllib.request.urlopen(request, timeout=15) as response:
                    body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ValueError('dependency index response exceeded bound')
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html' if path.startswith('/simple/') else 'application/octet-stream')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def runner(command, **kwargs):
        command = list(command)
        if command[:3] == ['uv', 'pip', 'install']:
            state['attempt'] += 1
            index = command.index('--default-index') + 1
            assert command[index] == 'https://pypi.org/simple'
            command[index] = f'http://127.0.0.1:{server.server_port}/simple'
        return run_process(command, **kwargs)

    try:
        return install_public_release(
            python=python, version=transport.version, evidence_path=output,
            validate=lambda: verify_postpublication(transport.dist_dir, transport.evidence,
                                                    version=transport.version, fetch=transport.fetch),
            runner=runner)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        coverage = json.dumps({'fixture_index': state, 'fixture_endpoints': transport.urls}, indent=2)
        output.with_name('fixture-endpoint-evidence.json').write_text(coverage + '\n')
        print(coverage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['guard', 'inventory', 'prepublication', 'postpublication', 'fault', 'install'])
    parser.add_argument('--dist-dir', type=Path, default=Path('dist'))
    parser.add_argument('--evidence', type=Path, default=Path('release-evidence/release-artifacts.json'))
    parser.add_argument('--python')
    parser.add_argument('--python-version')
    args = parser.parse_args()
    guard(fixture_required=args.mode != 'guard')
    if args.mode == 'guard':
        return 0
    scenario = os.environ.get('HARNESS_SCENARIO', 'success')
    if args.mode == 'fault':
        if args.python_version == '3.12':
            attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
            if (scenario == 'fail-once' and attempt == 1) or (scenario == 'fail-later' and attempt > 1):
                raise ValueError(f'controlled {scenario} verifier failure on attempt {attempt}')
            if scenario == 'cancel':
                print('Cancellation scenario ready: cancel this actual hosted job/run.', flush=True)
                time.sleep(600)
                raise ValueError('cancellation was not performed; never count this case as success')
        return 0
    version = os.environ['RELEASE_VERSION'].removeprefix('v')
    transport = FixtureTransport(args.dist_dir, args.evidence, version,
                                 mismatch=scenario == 'mismatch' and args.mode == 'install')
    if args.mode == 'inventory':
        result = transport.inventory(source_mismatch=scenario == 'source-mismatch')
    elif args.mode == 'install':
        return install_fixture(transport, python=args.python,
                               scenario=scenario if args.python_version == '3.12' else 'success',
                               output=Path(os.environ['RUNNER_TEMP']) / 'public-install-evidence.json')
    else:
        validate = verify_prepublication if args.mode == 'prepublication' else verify_postpublication
        result = validate(args.dist_dir, args.evidence, version=version, fetch=transport.fetch)
    print(json.dumps({'result': result, 'fixture_endpoints': transport.urls}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

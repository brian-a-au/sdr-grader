#!/usr/bin/env python3
"""Bound exact-version public discovery after frozen provenance/public byte checks.

The workflow's fetch action must validate source-bound provenance before calling
this script. Public byte validation is repeated here before any installer runs.
No grading behavior or package acceptance contract changes in this helper.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

ATTEMPTS = 6
DELAY_SECONDS = 10
TIMEOUT_SECONDS = 120


def sanitize(value: str | bytes | None) -> str:
    text = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
    # Retain diagnostic prose, never URL credentials, queries or auth headers.
    text = re.sub(r'https?://\S+', '[redacted-url]', text)
    text = re.sub(r'(?im)(authorization|token|password|secret)\s*[:=]\s*\S+', r'\1=[redacted]', text)
    return text


def version_not_discovered(output: str, version: str) -> bool:
    """Only the uv 0.11.16 grammar observed in run 34165517834 is retriable."""
    output = re.sub(r'^Using Python [0-9.]+ environment at: [^\n]+\n', '', output)
    normalized = ' '.join(output.split())
    expected = (
        '× No solution found when resolving dependencies: '
        f'╰─▶ Because there is no version of sdr-grader=={version} and you require '
        f'sdr-grader=={version}, we can conclude that your requirements are unsatisfiable.'
    )
    return normalized == expected


def run_process(command: list[str], *, capture_output: bool, text: bool,
                timeout: float, env: dict) -> subprocess.CompletedProcess:
    """Bound the installer and its descendants, including build subprocesses."""
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=text, env=env, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr) from None
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def install_public_release(
    *, python: str, version: str, evidence_path: Path,
    validate: Callable[[], object], runner: Callable = run_process,
    sleep: Callable = time.sleep, clock: Callable = time.monotonic,
) -> int:
    """Inject validation/process/time adapters for deterministic tests and U3.

    The production CLI exposes no index or validation bypass. U3 may pass a
    harness-only runner wrapper that substitutes its fixture index after real
    manifest/provenance/public fixture validation, retaining actual uv execution.
    """
    evidence: dict = {'version': version, 'attempts': [], 'outcome': 'validation-failed'}
    try:
        if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is None:
            raise ValueError('version must be exactly X.Y.Z')
        validate()
        evidence['outcome'] = 'installer-failed'
        # Configuration and inherited index/credential settings cannot redirect
        # production resolution away from the verified public endpoint.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('UV_', 'PIP_'))}
        command = ['uv', 'pip', 'install', '--no-config', '--color', 'never',
                   '--no-progress', '--default-index', 'https://pypi.org/simple',
                   '--refresh-package', 'sdr-grader', '--python', python,
                   f'sdr-grader=={version}']
        for number in range(1, ATTEMPTS + 1):
            started = clock()
            record = {'attempt': number}
            evidence['attempts'].append(record)
            try:
                result = runner(command, capture_output=True, text=True,
                                timeout=TIMEOUT_SECONDS, env=env)
            except subprocess.TimeoutExpired as exc:
                record.update(classification='timeout', stdout=sanitize(exc.stdout),
                              stderr=sanitize(exc.stderr), duration_seconds=clock() - started)
                evidence['outcome'] = 'timeout'
                return 1
            record.update(returncode=result.returncode, stdout=sanitize(result.stdout),
                          stderr=sanitize(result.stderr), duration_seconds=clock() - started)
            if result.returncode == 0:
                record['classification'] = 'installed'
                evidence['outcome'] = 'installed-version-check-failed'
                installed = runner([python, '-I', '-c',
                                    'from importlib.metadata import version; print(version("sdr-grader"))'],
                                   capture_output=True, text=True, timeout=TIMEOUT_SECONDS, env=env)
                evidence['installed_version'] = sanitize(installed.stdout.strip())
                evidence['version_check_stderr'] = sanitize(installed.stderr)
                if installed.returncode or installed.stdout.strip() != version:
                    evidence['outcome'] = 'wrong-installed-version'
                    return 1
                evidence['outcome'] = 'success'
                return 0
            absent = result.returncode == 1 and version_not_discovered(
                (result.stdout + result.stderr).strip(), version)
            record['classification'] = 'not-discovered' if absent else 'fatal'
            if not absent:
                evidence['outcome'] = 'fatal'
                return 1
            if number < ATTEMPTS:
                sleep(DELAY_SECONDS)
        evidence['outcome'] = 'exhausted'
        return 1
    except Exception as exc:
        evidence['error'] = sanitize(str(exc))
        return 1
    finally:
        evidence_path = Path(evidence_path)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(evidence, indent=2) + '\n'
        evidence_path.write_text(serialized, encoding='utf-8')
        # Ordered diagnostics remain in hosted logs even when later smoke fails.
        print(serialized, end='')


def main() -> int:
    from verify_published_readme import verify_postpublication

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--dist-dir', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    return install_public_release(
        python=args.python, version=args.version, evidence_path=args.output,
        validate=lambda: verify_postpublication(args.dist_dir, args.evidence, version=args.version),
    )


if __name__ == '__main__':
    raise SystemExit(main())

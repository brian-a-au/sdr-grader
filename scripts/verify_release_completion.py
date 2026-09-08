#!/usr/bin/env python3
"""Fail closed unless actual hosted jobs establish complete frozen verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

REQUIRED_JOBS = (
    'Artifact smoke / Python 3.11',
    'Artifact smoke / Python 3.12',
    'Frozen wheel Claude plugin smoke',
    'Verify tagged README before publication',
    'Verify PyPI publication before announcement',
    'Public endpoints / Python 3.11',
    'Public endpoints / Python 3.12',
)


class CompletionError(ValueError):
    """Required hosted evidence is absent, ambiguous, or unsuccessful."""


def gh_json(path):
    result = subprocess.run(['gh', 'api', path], check=True, capture_output=True,
                            text=True, timeout=60)
    return json.loads(result.stdout)


def list_jobs(repository, run_id, attempt, *, fetch=gh_json, page_size=100):
    """Read each attempt explicitly; never infer coverage from workflow color."""
    entries = []
    for number in range(1, attempt + 1):
        count = None
        received = []
        page = 1
        while count is None or len(received) < count:
            payload = fetch(f'repos/{repository}/actions/runs/{run_id}/attempts/{number}'
                            f'/jobs?per_page={page_size}&page={page}')
            if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
                raise CompletionError('invalid jobs API response')
            total = payload.get('total_count')
            if type(total) is not int or total < 0 or (count is not None and count != total):
                raise CompletionError('inconsistent job pagination')
            count = total
            batch = payload['jobs']
            if len(batch) > page_size or (not batch and len(received) < count):
                raise CompletionError('truncated job pagination')
            received.extend(batch)
            if len(received) > count:
                raise CompletionError('job count exceeded')
            page += 1
        entries.extend(received)
    return entries


def verify_completion(jobs, *, run_id, attempt, source_sha, source_ref, manifest_sha,
                      job_prefix=''):
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha) or not re.fullmatch(r'[0-9a-f]{64}', manifest_sha):
        raise CompletionError('invalid frozen identity')
    if not source_ref.startswith('refs/') or attempt < 1:
        raise CompletionError('invalid run identity')
    expected = {job_prefix + name for name in REQUIRED_JOBS}
    grouped = {name: {} for name in expected}
    ids = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise CompletionError('invalid job record')
        name = job.get('name')
        # Ignore unrelated build/publisher/terminal jobs, but reject unknown
        # members of either required matrix rather than silently dropping them.
        if name not in expected:
            if isinstance(name, str) and any(name.startswith(job_prefix + prefix)
                    for prefix in ('Artifact smoke / Python ', 'Public endpoints / Python ')):
                raise CompletionError(f'unknown matrix entry: {name}')
            continue
        number = job.get('run_attempt')
        identifier = job.get('id')
        if (job.get('run_id') != run_id or job.get('head_sha') != source_sha
                or type(number) is not int or not 1 <= number <= attempt
                or type(identifier) is not int):
            raise CompletionError(f'wrong job identity: {name}')
        if identifier in ids:
            if ids[identifier] != job:
                raise CompletionError('conflicting job API records')
            continue  # GitHub may repeat retained jobs in attempt responses.
        ids[identifier] = job
        if number in grouped[name]:
            raise CompletionError(f'duplicate execution in attempt: {name}')
        grouped[name][number] = job
    effective = []
    for base in REQUIRED_JOBS:
        name = job_prefix + base
        if not grouped[name]:
            raise CompletionError(f'missing verifier: {name}')
        job = grouped[name][max(grouped[name])]
        if job.get('status') != 'completed' or job.get('conclusion') != 'success':
            raise CompletionError(f'verifier did not succeed: {name}: {job.get("conclusion")}')
        effective.append({key: job.get(key) for key in
                          ('id', 'name', 'run_attempt', 'status', 'conclusion', 'head_sha', 'html_url')})
    return dict(status='success', run_id=run_id, run_attempt=attempt, source_sha=source_sha,
                source_ref=source_ref, manifest_sha256=manifest_sha, jobs=effective)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--attempt', type=int, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--job-prefix', default='')
    args = parser.parse_args()
    try:
        run = gh_json(f'repos/{args.repository}/actions/runs/{args.run_id}')
        if (run.get('id') != args.run_id or run.get('head_sha') != args.source_sha
                or run.get('run_attempt') != args.attempt
                or run.get('head_branch') != args.source_ref.split('/', 2)[-1]):
            raise CompletionError('hosted run differs from frozen identity')
        payload = args.evidence.read_bytes()
        manifest = json.loads(payload)
        if manifest.get('source_sha') != args.source_sha:
            raise CompletionError('manifest differs from frozen source')
        result = verify_completion(list_jobs(args.repository, args.run_id, args.attempt),
            run_id=args.run_id, attempt=args.attempt, source_sha=args.source_sha,
            source_ref=args.source_ref, manifest_sha=hashlib.sha256(payload).hexdigest(),
            job_prefix=args.job_prefix)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result = {'status': 'failure', 'error': str(exc)}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())

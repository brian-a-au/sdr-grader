import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verify_release_completion.py"
spec = importlib.util.spec_from_file_location("verify_release_completion_under_test", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
completion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(completion)
REQUIRED_JOBS = completion.REQUIRED_JOBS
CompletionError = completion.CompletionError
list_jobs = completion.list_jobs
verify_completion = completion.verify_completion


SHA = 'a' * 40

def jobs():
    return [dict(id=i, name=name, run_id=42, run_attempt=1, head_sha=SHA,
                 status='completed', conclusion='success')
            for i, name in enumerate(REQUIRED_JOBS, 1)]


def check(entries):
    return verify_completion(entries, run_id=42, attempt=2, source_sha=SHA,
                             source_ref='refs/tags/v1.3.0', manifest_sha='b' * 64)


def test_retained_peer_and_new_success_are_attributed():
    entries = jobs()
    new = dict(entries[-1], id=99, run_attempt=2)
    entries.append(new)
    result = check(entries)
    assert result['jobs'][-1]['id'] == 99
    assert result['jobs'][0]['run_attempt'] == 1


@pytest.mark.parametrize('conclusion', ['failure', 'skipped', 'cancelled', None, 'neutral'])
def test_newer_non_success_invalidates_old_success(conclusion):
    entries = jobs()
    entries.append(dict(entries[-1], id=99, run_attempt=2, conclusion=conclusion))
    with pytest.raises(CompletionError):
        check(entries)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown', 'sha', 'run', 'pending', 'attempt'])
def test_incomplete_or_ambiguous_evidence_fails(change):
    entries = deepcopy(jobs())
    if change == 'missing':
        entries.pop()
    elif change == 'duplicate':
        entries.append(dict(entries[-1], id=99))
    elif change == 'unknown':
        entries[-1]['name'] = 'Public endpoints / Python 3.13'
    else:
        key, value = {'sha': ('head_sha', 'c' * 40), 'run': ('run_id', 43),
                      'pending': ('status', 'queued'), 'attempt': ('run_attempt', 3)}[change]
        entries[-1][key] = value
    with pytest.raises(CompletionError):
        check(entries)


def test_paginated_attempts_and_errors():
    calls = []
    def fetch(path):
        calls.append(path)
        return {'total_count': 2, 'jobs': [{'id': len(calls)}]}
    result = list_jobs('owner/repo', 42, 2, fetch=fetch, page_size=1)
    assert len(result) == 4
    assert 'attempts/2/jobs?per_page=1&page=2' in calls[-1]
    with pytest.raises(CompletionError):
        list_jobs('owner/repo', 42, 1, fetch=lambda _: {'total_count': 2, 'jobs': []})
    with pytest.raises(RuntimeError):
        list_jobs('owner/repo', 42, 1, fetch=lambda _: (_ for _ in ()).throw(RuntimeError('API')))

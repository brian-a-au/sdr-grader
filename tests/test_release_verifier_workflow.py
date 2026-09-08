from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def retained_pair(tmp_path, monkeypatch, records, *, attempt=3, source='artifacts',
                  harness='false', event='push'):
    """Execute the production selector, so tests cannot drift to a copied loop."""
    import json

    action = yaml.safe_load((ROOT / '.github/actions/fetch-release-candidate/action.yml').read_text())
    step = next(step for step in action['runs']['steps'] if step.get('id') == 'retained')
    script = step['run'].split("python3 - <<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'retained-artifacts.json').write_text(json.dumps([{'artifacts': records}]))
    output = tmp_path / 'outputs'
    for key, value in {'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ATTEMPT': str(attempt),
                       'RETENTION_HARNESS': harness, 'GITHUB_EVENT_NAME': event,
                       'REQUESTED_SOURCE': source, 'GITHUB_OUTPUT': str(output)}.items():
        monkeypatch.setenv(key, value)
    exec(compile(script, '<production-retained-selector>', 'exec'), {})
    return dict(line.split('=', 1) for line in output.read_text().splitlines())


def artifact_pair(attempt=None, *, start=1, expired=False, sha='a' * 40):
    suffix = sha if attempt is None else f'{sha}-recovery-{attempt}'
    return [{'name': f'candidate-{kind}-{suffix}', 'id': start + index, 'expired': expired}
            for index, kind in enumerate(('dist', 'evidence'))]


def test_retained_prior_recovery_survives_later_failed_only_rerun(tmp_path, monkeypatch):
    records = artifact_pair(expired=True) + artifact_pair(2, start=20)
    assert retained_pair(tmp_path, monkeypatch, records) == {
        'available': 'true', 'dist_id': '20', 'evidence_id': '21'}


def test_retained_original_pair_wins_over_newer_recovery(tmp_path, monkeypatch):
    records = artifact_pair(3, start=30) + artifact_pair()
    assert retained_pair(tmp_path, monkeypatch, records)['dist_id'] == '1'


def test_retained_newest_complete_pair_ignores_missing_half_and_future(tmp_path, monkeypatch):
    records = (artifact_pair(1, start=10) + artifact_pair(2, start=20)
               + artifact_pair(3, start=30)[:1] + artifact_pair(4, start=40)
               + artifact_pair(3, start=50, sha='b' * 40))
    assert retained_pair(tmp_path, monkeypatch, records)['dist_id'] == '20'


@pytest.mark.parametrize('records', [artifact_pair(4), artifact_pair(2)[:1],
                                    artifact_pair(2, expired=True)])
def test_retained_unavailable_pair_fails_closed(tmp_path, monkeypatch, records):
    with pytest.raises(SystemExit, match='immutable artifacts unavailable'):
        retained_pair(tmp_path, monkeypatch, records)


def test_retained_ambiguous_pair_fails_closed(tmp_path, monkeypatch):
    records = artifact_pair(2, start=20) + artifact_pair(2, start=30)[:1]
    with pytest.raises(SystemExit, match='ambiguous retained artifact identity'):
        retained_pair(tmp_path, monkeypatch, records)


def test_retained_auto_allows_verified_release_recovery_when_no_pair(tmp_path, monkeypatch):
    assert retained_pair(tmp_path, monkeypatch, [], source='auto') == {'available': 'false'}


def test_harness_can_restore_backup_when_full_rerun_deleted_artifacts(tmp_path, monkeypatch):
    assert retained_pair(tmp_path, monkeypatch, [], harness='true', event='workflow_dispatch') == {
        'available': 'false'}


@pytest.mark.parametrize('harness,event', [('true', 'push'), ('false', 'workflow_dispatch')])
def test_production_cannot_select_harness_backup(tmp_path, monkeypatch, harness, event):
    with pytest.raises(SystemExit, match='immutable artifacts unavailable'):
        retained_pair(tmp_path, monkeypatch, [], harness=harness, event=event)


def test_harness_backup_is_exact_immutable_and_validated_before_consumption():
    build = workflow()['jobs']['build']
    assert build['if'] == 'github.run_attempt == 1'
    build_steps = build['steps']
    action_steps = yaml.safe_load(
        (ROOT / '.github/actions/fetch-release-candidate/action.yml').read_text())['runs']['steps']
    pin = '55cc8345863c7cc4c66a329aec7e433d2d1c52a9'
    key = 'harness-candidate-${{ github.repository_id }}-${{ github.run_id }}-${{ github.sha }}'
    save = next(step for step in build_steps if step.get('id') == 'save-harness-backup')
    lookup = next(step for step in build_steps if step.get('id') == 'check-harness-backup')
    restore = next(step for step in action_steps if step.get('id') == 'restore-harness-backup')
    assert save['uses'] == f'actions/cache/save@{pin}'
    for step in (save, lookup, restore):
        assert "github.event_name == 'workflow_dispatch'" in step['if']
        assert step['with']['key'] == key
        assert step['with']['path'] == '${{ github.workspace }}/.harness-candidate-backup'
        assert 'restore-keys' not in step['with']
    for step in (lookup, restore):
        assert step['uses'] == f'actions/cache/restore@{pin}'
        assert step['with']['fail-on-cache-miss'] is True
    assert lookup['with']['lookup-only'] is True
    assert "inputs.harness == 'true'" in restore['if']
    assert "steps.retained.outputs.available == 'false'" in restore['if']
    save_gate = next(step for step in build_steps if step.get('name') == 'Require saved harness backup')
    assert "steps.check-harness-backup.outputs.cache-hit" in str(save_gate['env'])
    assert 'test "${CACHE_HIT}" = true' in save_gate['run']
    restore_gate = next(step for step in action_steps if step.get('name') == 'Materialize exact harness backup')
    assert "steps.restore-harness-backup.outputs.cache-hit" in str(restore_gate['env'])
    assert 'test "${CACHE_HIT}" = true' in restore_gate['run']
    names = [step.get('name') for step in action_steps]
    assert names.index('Materialize exact harness backup') < names.index('Verify recovered distribution provenance')
    assert names.index('Verify recovered distribution provenance') < names.index('Verify fetched candidate identity')
    for name in ('Recover distributions and evidence from the existing release',
                 'Verify exact release inventory and publication state'):
        step = next(step for step in action_steps if step.get('name') == name)
        assert "inputs.harness != 'true'" in step['if']


@pytest.mark.parametrize('cache_hit', ['true', 'false', ''])
def test_harness_backup_materializes_identical_bytes_only_on_exact_hit(tmp_path, cache_hit):
    import importlib.util
    import os
    import shutil
    import subprocess

    spec = importlib.util.spec_from_file_location('readme_tests', ROOT / 'tests/test_published_readme.py')
    existing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(existing)
    dist, wheel, evidence = existing._artifacts(tmp_path, '# Frozen harness candidate\n')
    evidence_dir = tmp_path / 'release-evidence'
    evidence_dir.mkdir()
    evidence.rename(evidence_dir / evidence.name)
    originals = {path.name: path.read_bytes() for directory in (dist, evidence_dir)
                 for path in directory.iterdir()}
    prepare = next(step for step in workflow()['jobs']['build']['steps']
                   if step.get('name') == 'Prepare immutable harness backup')
    subprocess.run(['bash', '-c', prepare['run']], cwd=tmp_path, check=True)
    backup = tmp_path / '.harness-candidate-backup'
    assert {path.name: path.read_bytes() for path in backup.iterdir()} == originals
    shutil.rmtree(dist)
    shutil.rmtree(evidence_dir)
    action_steps = yaml.safe_load(
        (ROOT / '.github/actions/fetch-release-candidate/action.yml').read_text())['runs']['steps']
    materialize = next(step for step in action_steps if step.get('name') == 'Materialize exact harness backup')
    result = subprocess.run(['bash', '-c', materialize['run']], cwd=tmp_path,
                            env={**os.environ, 'CACHE_HIT': cache_hit, 'DIST_DIR': str(dist),
                                 'EVIDENCE_DIR': str(evidence_dir)}, capture_output=True, text=True)
    if cache_hit != 'true':
        assert result.returncode != 0
        assert not dist.exists() and not evidence_dir.exists()
        return
    assert result.returncode == 0, result.stderr
    assert {path.name: path.read_bytes() for directory in (dist, evidence_dir)
            for path in directory.iterdir()} == originals
    module = fixture_module()
    evidence = evidence_dir / 'release-artifacts.json'
    module.verify_candidate(dist, evidence, version=existing.VERSION, source_sha=existing.SOURCE_SHA)
    with pytest.raises(Exception, match='source commit differs'):
        module.verify_candidate(dist, evidence, version=existing.VERSION, source_sha='0' * 40)
    wheel.write_bytes(b'tampered restored bytes')
    with pytest.raises(Exception):
        module.verify_candidate(dist, evidence, version=existing.VERSION, source_sha=existing.SOURCE_SHA)


def workflow():
    return yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())


def fixture_module():
    import importlib.util
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('fixture', ROOT / 'scripts/release_verifier_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_and_harness_share_actual_graph():
    document = workflow()
    triggers = document.get('on', document.get(True))
    assert set(triggers) == {'push', 'workflow_dispatch'}
    assert triggers['push'] == {'tags': ['v*.*.*']}
    assert set(triggers['workflow_dispatch']['inputs']) == {'version', 'scenario'}
    assert document['env']['HARNESS_MODE'] == "${{ github.event_name == 'workflow_dispatch' }}"
    jobs = document['jobs']
    assert jobs['verify-public']['needs'] == 'publish-github'
    assert jobs['verify-public']['if'] == '${{ always() && !cancelled() }}'
    assert jobs['verify-completion']['if'] == '${{ always() }}'
    assert jobs['build']['if'] == 'github.run_attempt == 1'
    assert 'workflow_call' not in triggers


def test_dispatch_cannot_publish_and_tag_cannot_select_fixtures():
    jobs = workflow()['jobs']
    mutations = {
        'draft-github': ['Inspect existing GitHub release', 'Create draft from tested bytes'],
        'publish-pypi': ['Verify recoverable PyPI state', 'Publish exact candidate to PyPI', 'Attest published distributions'],
        'publish-github': ['Publish the existing draft'],
    }
    for name, steps in mutations.items():
        for step in jobs[name]['steps']:
            if step.get('name') in steps:
                assert "github.event_name != 'workflow_dispatch'" in step['if']
    for job in jobs.values():
        for step in job['steps']:
            if 'fixture.py' in step.get('run', '') and step.get('name') != 'Enforce caller mode and frozen identity':
                if 'install_public_release.py' in step['run']:
                    assert 'if [ "${HARNESS_MODE}" = true ]' in step['run']
                else:
                    assert step['if'] == "${{ github.event_name == 'workflow_dispatch' }}"
    for name in ('install-smoke', 'plugin-smoke', 'verify-public', 'verify-completion'):
        assert set(jobs[name]['permissions'].values()) == {'read'}


@pytest.mark.parametrize('event,ref,harness,allowed', [
    ('push', 'refs/tags/v1.3.0', 'false', True),
    ('push', 'refs/tags/v1.3.0', 'true', False),
    ('workflow_dispatch', 'refs/tags/v1.3.0', 'true', False),
    ('workflow_dispatch', 'refs/heads/main', 'true', True),
    ('workflow_dispatch', 'refs/heads/main', 'false', False),
    ('pull_request', 'refs/pull/1/merge', 'true', False),
])
def test_transport_guard_fails_closed(monkeypatch, event, ref, harness, allowed):
    module = fixture_module()
    for key, value in {'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref, 'HARNESS_MODE': harness,
                       'GITHUB_REPOSITORY': 'brian-a-au/sdr-grader',
                       'GITHUB_WORKFLOW_REF': 'brian-a-au/sdr-grader/.github/workflows/release.yml@' + ref}.items():
        monkeypatch.setenv(key, value)
    if allowed:
        module.guard()
    else:
        with pytest.raises(ValueError):
            module.guard()


def test_fixture_validators_check_actual_bytes_and_record_endpoints(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('readme_tests', ROOT / 'tests/test_published_readme.py')
    existing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(existing)
    dist, wheel, evidence = existing._artifacts(tmp_path, '[docs](https://github.com/brian-a-au/sdr-grader/blob/v1.2.3/README.md)\n')
    module = fixture_module()
    monkeypatch.setenv('GITHUB_SHA', existing.SOURCE_SHA)
    fixture = module.FixtureTransport(dist, evidence, existing.VERSION)
    fixture.inventory()
    result = module.verify_postpublication(dist, evidence, version=existing.VERSION, fetch=fixture.fetch)
    assert result['mode'] == 'postpublication'
    assert any(url.startswith('https://files.pythonhosted.org/') for url in fixture.urls)
    assert any(url.startswith('https://pypi.org/pypi/') for url in fixture.urls)
    with pytest.raises(Exception, match='source commit differs'):
        fixture.inventory(source_mismatch=True)
    bad = module.FixtureTransport(dist, evidence, existing.VERSION, mismatch=True)
    with pytest.raises(Exception, match='metadata differs'):
        module.verify_postpublication(dist, evidence, version=existing.VERSION, fetch=bad.fetch)
    wheel.write_bytes(b'changed recovered bytes')
    with pytest.raises(Exception):
        module.FixtureTransport(dist, evidence, existing.VERSION)


@pytest.mark.parametrize('scenario,expected_attempts,expected_outcome', [
    ('success', 1, 'success'),
    ('discovery', 2, 'success'), ('exhausted', 6, 'exhausted'), ('mismatch', 0, 'validation-failed'),
])
def test_index_transport_preserves_installer_budget_and_validation(
        tmp_path, monkeypatch, scenario, expected_attempts, expected_outcome):
    import importlib.util
    import json
    import subprocess
    import urllib.request
    spec = importlib.util.spec_from_file_location('readme_tests', ROOT / 'tests/test_published_readme.py')
    existing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(existing)
    dist, _wheel, evidence = existing._artifacts(tmp_path, '# Fixture description\n')
    module = fixture_module()
    transport = module.FixtureTransport(dist, evidence, existing.VERSION, mismatch=scenario == 'mismatch')
    calls = []

    def process(command, **kwargs):
        if command[0] != 'uv':
            return subprocess.CompletedProcess(command, 0, existing.VERSION + '\n', '')
        assert kwargs['timeout'] == 120
        assert '--refresh-package' in command
        assert command[-1] == 'sdr-grader==' + existing.VERSION
        index = command[command.index('--default-index') + 1]
        assert index.startswith('http://127.0.0.1:')
        with urllib.request.urlopen(index + '/sdr-grader/', timeout=2) as response:
            body = response.read().decode()
        calls.append(body)
        if '0.0.0' in body:
            diagnostic = ('× No solution found when resolving dependencies:\n'
                          f'╰─▶ Because there is no version of sdr-grader=={existing.VERSION} and you require '
                          f'sdr-grader=={existing.VERSION}, we can conclude that your requirements are unsatisfiable.')
            return subprocess.CompletedProcess(command, 1, '', diagnostic)
        assert _wheel.name in body
        for url, content_type in (
            (index + '/sdr-grader/', 'text/html'),
            (index.removesuffix('/simple') + '/files/' + _wheel.name, 'application/octet-stream'),
        ):
            with urllib.request.urlopen(url, timeout=2) as response:
                get_body = response.read()
                get_headers = response.headers
            request = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(request, timeout=2) as response:
                assert response.status == 200
                assert response.headers['Content-Type'] == get_headers['Content-Type'] == content_type
                assert response.headers['Content-Length'] == get_headers['Content-Length'] == str(len(get_body))
                assert response.read() == b''
            if content_type == 'application/octet-stream':
                assert get_body == _wheel.read_bytes()
        return subprocess.CompletedProcess(command, 0, '', '')

    actual_install = module.install_public_release
    monkeypatch.setattr(module, 'install_public_release', lambda **kwargs: actual_install(**kwargs, sleep=lambda _: None))
    monkeypatch.setattr(module, 'run_process', process)
    output = tmp_path / 'install-evidence.json'
    code = module.install_fixture(transport, python='/fixture/python', scenario=scenario, output=output)
    result = json.loads(output.read_text())
    assert len(calls) == len(result['attempts']) == expected_attempts
    assert result['outcome'] == expected_outcome
    assert code == (0 if expected_outcome == 'success' else 1)

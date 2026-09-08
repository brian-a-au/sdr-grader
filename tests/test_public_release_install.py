import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install_public_release.py'
spec = importlib.util.spec_from_file_location('public_install_under_test', SCRIPT)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

ABSENT = '''  × No solution found when resolving dependencies:
  ╰─▶ Because there is no version of sdr-grader==1.3.0 and you require
      sdr-grader==1.3.0, we can conclude that your requirements are
      unsatisfiable.
'''


def exercise(tmp_path, outputs, validate=lambda: None):
    calls, delays = [], []
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        value = outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return subprocess.CompletedProcess(command, value[0], value[1], value[2])
    evidence = tmp_path / 'install.json'
    result = installer.install_public_release(
        python='/tmp/test/bin/python', version='1.3.0', evidence_path=evidence,
        validate=validate, runner=runner, sleep=delays.append,
    )
    return result, calls, delays, evidence.read_text()


def test_absent_then_present_verifies_exact_version(tmp_path):
    result, calls, delays, evidence = exercise(tmp_path, [(1, '', ABSENT), (0, '', ''), (0, '1.3.0\n', '')])
    assert result == 0 and delays == [10]
    assert len(calls) == 3
    for command, kwargs in calls[:2]:
        assert command[command.index('--refresh-package') + 1] == 'sdr-grader'
        assert command[command.index('--default-index') + 1] == 'https://pypi.org/simple'
        assert kwargs['timeout'] == 120
    assert 'success' in evidence


def test_exhaustion_keeps_all_six_diagnostics(tmp_path):
    result, calls, delays, evidence = exercise(tmp_path, [(1, '', ABSENT)] * 6)
    assert result == 1 and len(calls) == 6 and delays == [10] * 5
    assert evidence.count('not-discovered') == 6
    assert 'exhausted' in evidence


@pytest.mark.parametrize('diagnostic', [
    ABSENT.replace('1.3.0', '1.3.1'), ABSENT.replace('sdr-grader', 'other'),
    ABSENT + '\nHTTP 401 Unauthorized', ABSENT + '\nHash mismatch',
    'dependency conflict', 'network timeout', 'unknown resolver failure',
])
def test_other_failures_never_retry(tmp_path, diagnostic):
    result, calls, delays, _ = exercise(tmp_path, [(1, '', diagnostic)])
    assert result == 1 and len(calls) == 1 and not delays


def test_validation_failure_precedes_install(tmp_path):
    def invalid():
        raise ValueError('hash/provenance mismatch')
    result, calls, delays, evidence = exercise(tmp_path, [], validate=invalid)
    assert result == 1 and not calls and not delays
    assert 'validation-failed' in evidence


def test_wrong_installed_version_is_fatal(tmp_path):
    result, calls, delays, evidence = exercise(tmp_path, [(0, '', ''), (0, '1.2.9\n', '')])
    assert result == 1 and len(calls) == 2 and not delays
    assert 'wrong-installed-version' in evidence


def test_timeout_never_retries_and_retains_sanitized_diagnostic(tmp_path):
    error = subprocess.TimeoutExpired('uv', 120, stderr=b'https://user:secret@example.test/file?token=secret')
    result, calls, delays, evidence = exercise(tmp_path, [error])
    assert result == 1 and len(calls) == 1 and not delays
    assert 'secret' not in evidence and 'timeout' in evidence


def test_observed_uv_environment_preamble_is_supported():
    assert installer.version_not_discovered(
        'Using Python 3.12.3 environment at: /home/runner/work/_temp/public-venv\n' + ABSENT,
        '1.3.0',
    )


def test_real_hung_subprocess_is_reaped():
    with pytest.raises(subprocess.TimeoutExpired):
        installer.run_process([sys.executable, '-c', 'import time; time.sleep(30)'],
                              capture_output=True, text=True, timeout=0.05, env=dict(os.environ))


def test_environment_cannot_override_production_index(tmp_path, monkeypatch):
    monkeypatch.setenv('UV_INDEX', 'https://example.test')
    monkeypatch.setenv('PIP_EXTRA_INDEX_URL', 'https://example.test')
    result, calls, _, _ = exercise(tmp_path, [(1, '', 'fatal')])
    assert result == 1
    assert not any(k.startswith(('UV_', 'PIP_')) for k in calls[0][1]['env'])


def test_invalid_version_prevents_validation_and_processes(tmp_path):
    evidence = tmp_path / 'invalid.json'
    def forbidden(*args, **kwargs):
        pytest.fail('invalid version reached external code')
    assert installer.install_public_release(
        python='/tmp/python', version='1.3.0 --index=evil', evidence_path=evidence,
        validate=forbidden, runner=forbidden,
    ) == 1


def test_timeout_also_kills_build_descendants(tmp_path):
    marker = tmp_path / 'child-survived'
    child = f'import time; from pathlib import Path; time.sleep(0.3); Path({str(marker)!r}).touch()'
    parent = f'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", {child!r}]); time.sleep(30)'
    with pytest.raises(subprocess.TimeoutExpired):
        installer.run_process([sys.executable, '-c', parent], capture_output=True,
                              text=True, timeout=0.1, env=dict(os.environ))
    time.sleep(0.4)
    assert not marker.exists()

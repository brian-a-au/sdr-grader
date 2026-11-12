from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_commit_identity.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_identity", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


identity = _load()


@pytest.mark.parametrize(
    ("name", "email"),
    [
        ("Brian Au", "brian.a.au@gmail.com"),
        ("brian-a-au", "114970593+brian-a-au@users.noreply.github.com"),
        ("GitHub", "noreply@github.com"),
        ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
        ("Outside Contributor", "someone@example.org"),
    ],
)
def test_allowed_identities_pass(name, email):
    assert identity.identity_problem("author", name, email) is None


@pytest.mark.parametrize(
    ("name", "email"),
    [
        ("Brian Au", "bau@adobe.com"),
        ("Anyone", "Someone@Adobe.com"),
        ("Brian Au", "other@example.com"),
        ("bau", "bau@example.com"),
    ],
)
def test_wrong_maintainer_identities_fail(name, email):
    assert identity.identity_problem("committer", name, email)


def test_problems_report_each_role_with_short_sha():
    records = [("a" * 40, "Brian Au", "bau@adobe.com", "GitHub", "noreply@github.com")]
    assert identity.problems_for(records) == [
        "aaaaaaaaaaaa: author email 'bau@adobe.com' uses a blocked employer domain"
    ]


def _commit(repo: Path, email: str) -> None:
    env_args = ["-c", "user.name=Brian Au", "-c", f"user.email={email}"]
    env_args += ["-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    subprocess.run(
        ["git", *env_args, "commit", "--allow-empty", "-q", "-m", "x"],
        cwd=repo,
        check=True,
    )


def test_range_mode_flags_only_bad_commits(tmp_path, monkeypatch, capsys):
    for variable in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(variable, raising=False)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _commit(tmp_path, "brian.a.au@gmail.com")
    _commit(tmp_path, "bau@adobe.com")
    monkeypatch.chdir(tmp_path)

    assert identity.main(["HEAD~1..HEAD"]) == 1
    err = capsys.readouterr().err
    assert "author email 'bau@adobe.com'" in err
    assert "committer email 'bau@adobe.com'" in err

    assert identity.main(["HEAD~1"]) == 0


def test_identity_workflow_is_read_only_and_checks_the_pr_range():
    text = (REPO_ROOT / ".github" / "workflows" / "commit-identity.yml").read_text()
    assert "pull_request:" in text
    assert "permissions:\n  contents: read" in text
    assert "persist-credentials: false" in text
    assert 'check_commit_identity.py "$BASE_SHA..$HEAD_SHA"' in text

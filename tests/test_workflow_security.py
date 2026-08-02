from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
FULL_SHA_USE = re.compile(
    r"^\s*(?:-\s+)?uses:\s+[^@\s]+@[0-9a-f]{40}(?:\s+#\s+.+)?$",
    re.MULTILINE,
)
ANY_USE = re.compile(
    r"^\s*(?:-\s+)?uses:\s+\S+@\S+.*$",
    re.MULTILINE,
)


def _workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_every_workflow_action_is_pinned_and_checkout_drops_credentials():
    workflows = sorted(WORKFLOWS.glob("*.yml"))
    assert workflows

    for path in workflows:
        text = path.read_text(encoding="utf-8")
        uses = ANY_USE.findall(text)
        assert uses, f"{path.name} has no auditable action identity"
        assert all(FULL_SHA_USE.fullmatch(line) for line in uses), (
            f"{path.name} contains a mutable action reference: {uses}"
        )
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if "uses: actions/checkout@" not in line:
                continue
            block = "\n".join(lines[index : index + 8])
            assert "persist-credentials: false" in block, (
                f"{path.name} checkout persists repository credentials"
            )


def test_pr_workflows_have_read_only_defaults_and_stable_check_names():
    required_checks = {
        "lint.yml": "name: Lint",
        "test.yml": "name: Tests / Python ${{ matrix.python-version }}",
        "version-sync.yml": "name: Version identity",
        "dependency-review.yml": "name: Dependency review",
        "codeql.yml": "name: CodeQL / Python",
    }
    for filename, check_name in required_checks.items():
        text = _workflow_text(filename)
        assert "pull_request:" in text
        assert re.search(
            r"^permissions:\n\s+contents:\s+read$",
            text,
            re.MULTILINE,
        )
        assert check_name in text


def test_release_workflow_is_tag_only_build_once_and_authority_isolated():
    text = _workflow_text("release.yml")
    assert "pull_request:" not in text
    assert "branches:" not in text
    assert "tags:" in text
    assert text.count("id-token: write") == 1
    assert "PYPI_API_TOKEN" not in text
    assert "password:" not in text.lower()
    assert "uv build --no-sources --clear --no-create-gitignore" in text
    assert "scripts/verify_release_artifacts.py" in text
    assert "draft: true" in text
    assert "environment:\n      name: pypi" in text
    assert "environment:\n      name: github-release" in text
    assert "--draft=false" in text
    assert "verify-public:" in text

    candidate = text.split("\n  candidate:", 1)[1].split(
        "\n  install-smoke:",
        1,
    )[0]
    assert "contents: write" not in candidate
    assert "id-token: write" not in candidate
    publisher = text.split("\n  publish-pypi:", 1)[1].split(
        "\n  publish-github:",
        1,
    )[0]
    assert "id-token: write" in publisher
    assert "attestations: write" in publisher


def test_release_workflow_builds_before_isolated_frozen_wheel_plugin_smoke():
    text = _workflow_text("release.yml")

    candidate = text.split("\n  candidate:", 1)[1].split(
        "\n  build:",
        1,
    )[0]
    build = text.split("\n  build:", 1)[1].split(
        "\n  install-smoke:",
        1,
    )[0]
    plugin_smoke = text.split("\n  plugin-smoke:", 1)[1].split(
        "\n  draft-github:",
        1,
    )[0]
    draft = text.split("\n  draft-github:", 1)[1].split(
        "\n  publish-pypi:",
        1,
    )[0]

    assert "uv build --no-sources --clear --no-create-gitignore" not in candidate
    assert "npm install" not in candidate
    assert "needs: candidate" in build
    assert "uv build --no-sources --clear --no-create-gitignore" in build
    assert "npm install" not in build
    assert "claude plugin" not in build
    assert "needs: build" in plugin_smoke
    assert "Download immutable distributions" in plugin_smoke
    assert "uv pip install" in plugin_smoke
    assert "dist/*.whl" in plugin_smoke
    assert "npm install --global @anthropic-ai/claude-code@" in plugin_smoke
    assert 'STRICT_PLUGIN_ROOT="${RUNNER_TEMP}/strict-plugin"' in plugin_smoke
    assert 'claude plugin validate "${STRICT_PLUGIN_ROOT}" --strict' in plugin_smoke
    assert "claude plugin install sdr-grader@sdr-grader" in plugin_smoke
    assert "plugin compare smoke" in plugin_smoke
    assert "--suppress-config" in plugin_smoke
    assert '"${RUNNER_TEMP}/plugin-grade-suppressed.json"' in plugin_smoke
    assert "needs: [install-smoke, plugin-smoke]" in draft


def test_release_workflow_digest_gates_idempotent_pypi_recovery():
    text = _workflow_text("release.yml")

    assert "scripts/check_pypi_release_state.py" in text
    assert "if: steps.pypi-state.outputs.state != 'matching'" in text
    assert "skip-existing: true" in text
    assert text.index("Verify recoverable PyPI state") < text.index(
        "Publish exact candidate to PyPI"
    )


def test_release_soak_is_frozen_least_privilege_and_self_terminating():
    text = _workflow_text("release-soak.yml")

    assert 'cron: "23 * * * *"' in text
    assert "if: github.ref == 'refs/heads/main'" in text
    assert "ref: 9301672144d5fe97cc869a9f5206da38d26fd353" in text
    assert "pypi-attestations==0.0.30" in text
    assert "--source-ref \"refs/tags/${GRADER_TAG}\"" in text
    assert "--source-digest \"${GRADER_COMMIT}\"" in text
    assert "VISUALIZER_COMMIT" in text
    assert "certificate.txt" in text
    assert "URI:https://github.com/${repository}/.github/workflows/release.yml@refs/tags/${tag}" in text
    assert "security-events: read" in text
    assert "vulnerability-alerts: read" in text
    assert "secret-scanning/alerts" not in text
    assert "sdr-grader-v1.2.1-private-advisory-clear" in text
    assert '.user.login == "brian-a-au"' in text
    assert "CLEARANCE_CUTOFF" in text
    assert ".github/scripts/verify_release_soak_timeline.py" in text
    assert "retention-days: 90" in text
    assert "actions/workflows/release-soak.yml/disable" in text

    verify = text.split("\n  verify:", 1)[1].split("\n  hosted-state:", 1)[0]
    hosted = text.split("\n  hosted-state:", 1)[1].split(
        "\n  checkpoint:",
        1,
    )[0]
    finalize = text.split("\n  finalize:", 1)[1]
    assert "security-events:" not in verify
    assert "issues: write" not in verify
    assert "actions: write" not in verify
    assert "npm install" not in hosted
    assert "uvx" not in hosted
    assert "issues: read" in hosted
    assert "actions: write" in finalize
    assert "issues: write" in finalize


def test_codeql_dependency_updates_and_governance_files_are_configured():
    codeql = _workflow_text("codeql.yml")
    assert "security-events: write" in codeql
    assert "languages: python" in codeql

    dependabot = yaml.safe_load(
        (REPO_ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf-8"
        )
    )
    ecosystems = {
        update["package-ecosystem"] for update in dependabot["updates"]
    }
    assert ecosystems == {"github-actions", "uv"}

    codeowners = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(
        encoding="utf-8"
    )
    assert "* @brian-a-au" in codeowners
    assert "/.github/workflows/ @brian-a-au" in codeowners

    conduct = (REPO_ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    checklist = (REPO_ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )
    assert "Enforcement" in conduct
    assert "1.2.x" in security
    assert "private security advisory" in security.lower()
    for required in (
        "Candidate identity",
        "Artifact evidence",
        "Hosted controls",
        "History and namespace scan",
        "Recovery procedure",
        "Publication approval",
        "Announcement approval",
    ):
        assert required in checklist

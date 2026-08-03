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
    assert "needs: [candidate, build]" in plugin_smoke
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
    assert "needs: verify-prepublication" in draft


def test_release_workflow_digest_gates_idempotent_pypi_recovery():
    text = _workflow_text("release.yml")

    assert "scripts/check_pypi_release_state.py" in text
    assert "if: steps.pypi-state.outputs.state != 'matching'" in text
    assert "skip-existing: true" in text
    assert text.index("Verify recoverable PyPI state") < text.index(
        "Publish exact candidate to PyPI"
    )


def test_release_workflow_pins_validation_and_builds_candidate_only_once():
    text = _workflow_text("release.yml")

    assert text.count("uv build --no-sources --clear --no-create-gitignore") == 1
    assert "if: github.run_attempt == 1" in text
    assert "uv sync --locked --all-extras --dev" in text
    assert "--require-hashes -r requirements/release-validation.txt" in text
    assert "twine check --strict dist/*" in text

    setup_blocks = re.findall(
        r"- name: Install uv\n(?P<body>(?:\s+.*\n){1,8})",
        text,
    )
    assert setup_blocks
    assert all("version: 0.11.16" in block for block in setup_blocks)

    for job_name in (
        "install-smoke",
        "plugin-smoke",
        "verify-prepublication",
        "draft-github",
        "publish-pypi",
        "verify-pypi-publication",
        "verify-public",
    ):
        job = text.split(f"\n  {job_name}:", 1)[1]
        next_job = re.search(r"\n  [a-z][a-z0-9-]+:", job)
        if next_job:
            job = job[: next_job.start()]
        assert "uv build " not in job
        assert "candidate-dist-${{ github.sha }}" in job

    recovery_condition = (
        "needs.build.result == 'success' || "
        "(github.run_attempt > 1 && needs.build.result == 'skipped')"
    )
    for job_name in ("install-smoke", "plugin-smoke"):
        job = text.split(f"\n  {job_name}:", 1)[1]
        next_job = re.search(r"\n  [a-z][a-z0-9-]+:", job)
        if next_job:
            job = job[: next_job.start()]
        assert "always()" in job
        assert "needs: [candidate, build]" in job
        assert "needs.candidate.result == 'success'" in job
        assert recovery_condition in " ".join(job.split())


def test_release_workflow_reuses_an_existing_draft_during_recovery():
    text = _workflow_text("release.yml")
    draft = text.split("\n  draft-github:", 1)[1].split(
        "\n  publish-pypi:",
        1,
    )[0]

    assert "Inspect existing GitHub release" in draft
    assert "gh release view" in draft
    assert "Verify existing GitHub release assets" in draft
    assert "steps.release-state.outputs.exists == 'true'" in draft
    assert "scripts/verify_github_release_assets.py" in draft
    assert "release-evidence/release-artifacts.json" in draft
    assert "release-metadata.json" in draft
    assert "release not found" in draft
    assert "gh release download" not in draft
    assert "steps.release-state.outputs.exists != 'true'" in draft
    assert draft.index("Inspect existing GitHub release") < draft.index(
        "Verify existing GitHub release assets"
    ) < draft.index(
        "Create draft from tested bytes"
    )


def test_release_workflow_runs_bounded_readme_checks_before_and_after_publication():
    text = _workflow_text("release.yml")
    pre = text.split("\n  verify-prepublication:", 1)[1].split("\n  draft-github:", 1)[0]
    draft = text.split("\n  draft-github:", 1)[1].split("\n  publish-pypi:", 1)[0]
    publish = text.split("\n  publish-pypi:", 1)[1].split("\n  verify-pypi-publication:", 1)[0]
    post = text.split("\n  verify-pypi-publication:", 1)[1].split("\n  publish-github:", 1)[0]
    github_release = text.split("\n  publish-github:", 1)[1].split("\n  verify-public:", 1)[0]

    assert "needs: [install-smoke, plugin-smoke]" in pre
    assert "scripts/verify_published_readme.py prepublication" in pre
    assert "--evidence release-evidence/release-artifacts.json" in pre
    assert "needs: verify-prepublication" in draft
    assert "needs: publish-pypi" in post
    assert "scripts/verify_published_readme.py postpublication" in post
    assert "--evidence release-evidence/release-artifacts.json" in post
    assert "needs: verify-pypi-publication" in github_release
    assert (
        text.index("\n  publish-pypi:")
        < text.index("\n  verify-pypi-publication:")
        < text.index("\n  publish-github:")
    )
    assert "postpublication" not in publish
    assert "GH_TOKEN" not in pre
    assert "GH_TOKEN" not in post
    assert "continue-on-error" not in pre
    assert "continue-on-error" not in post


def test_release_soak_is_frozen_least_privilege_and_self_terminating():
    text = _workflow_text("release-soak.yml")

    assert 'cron: "23 * * * *"' in text
    assert "if: github.ref == 'refs/heads/main'" in text
    assert "ref: 1978eb6d6e8d865e66f2dd464624db9a377417de" in text
    assert "pypi-attestations==0.0.30" in text
    assert "--source-ref \"refs/tags/${GRADER_TAG}\"" in text
    assert "--source-digest \"${GRADER_COMMIT}\"" in text
    assert "VISUALIZER_COMMIT" in text
    assert "certificate.txt" in text
    assert "URI:https://github.com/${repository}/.github/workflows/release.yml@refs/tags/${tag}" in text
    assert "security-events: read" in text
    assert "vulnerability-alerts: read" in text
    assert "secret-scanning/alerts" not in text
    assert 'SOAK_MARKER_PREFIX: "sdr-grader-v1.2.2"' in text
    assert '--arg marker_prefix "${SOAK_MARKER_PREFIX}"' in text
    assert '$marker_prefix + "-private-advisory-clear"' in text
    assert '$marker_prefix + "-announcement-go"' in text
    assert '--marker-prefix "${SOAK_MARKER_PREFIX}"' in text
    assert 'GRADER_VERSION: "1.2.2"' in text
    assert 'GRADER_TAG: "v1.2.2"' in text
    assert (
        'GRADER_TAG_OBJECT: "21914dd1e1a48fe9c9050225c86c9f6f2665b26d"'
        in text
    )
    assert (
        'GRADER_WHEEL_SHA: '
        '"6e8c3dfa3808dd338e57894856a5cc212bde0cc21e616f45a57b4f404de440dc"'
        in text
    )
    assert (
        'GRADER_SDIST_SHA: '
        '"d6566134cad3fd65cab8d44d983264f2dcd3a83af678d30846455aa28df20789"'
        in text
    )
    assert (
        'GRADER_EVIDENCE_SHA: '
        '"b255bc78a5e534229e3454f1b3173e46fc333d938c4fde332fb920c6e02d4496"'
        in text
    )
    assert 'SOAK_START_ISO: "2026-08-03T20:09:09Z"' in text
    assert 'SOAK_END_ISO: "2026-08-05T20:09:09Z"' in text
    assert "pull/41#issuecomment-5171182302" in text
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

"""Release-facing documentation invariants."""

from __future__ import annotations

import re
import shlex
from collections import defaultdict
from dataclasses import fields, replace
from pathlib import Path

import yaml

from fixtures.demo_report import build_demo_report
from sdr_grader.cli.main import _build_parser
from sdr_grader.core.grader import _PLATFORM_NOUN, _PLATFORM_TOOL
from sdr_grader.core.models import Component
from sdr_grader.render.json_output import REPORT_SCHEMA_VERSION, report_to_dict
from sdr_grader.rules.checks._helpers import PLATFORM_NOUN
from sdr_grader.rules.rubric import VALID_PLATFORMS, load_rubric

REPO_ROOT = Path(__file__).resolve().parent.parent


def _markdown_table(document: str, heading: str) -> list[dict[str, str]]:
    section = document.split(heading, 1)[1]
    lines = section.splitlines()
    table_lines: list[str] = []
    for line in lines:
        if line.startswith("|"):
            table_lines.append(line)
        elif table_lines:
            break
    assert len(table_lines) >= 3, f"missing table after {heading}"
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    assert all(
        re.fullmatch(r":?-+:?", cell.strip()) for cell in table_lines[1].strip("|").split("|")
    )
    return [
        dict(zip(headers, (cell.strip() for cell in line.strip("|").split("|")), strict=True))
        for line in table_lines[2:]
    ]


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    raise AssertionError(f"unsupported serialized type: {type(value)}")


def _collect_json_paths(
    value: object,
    path: str,
    result: defaultdict[str, set[str]],
) -> None:
    if path:
        result[path].add(_json_type(value))
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            _collect_json_paths(child, child_path, result)
    elif isinstance(value, list):
        for child in value:
            _collect_json_paths(child, f"{path}[]", result)


def _fenced_yaml(document: str, marker: str) -> dict[str, object]:
    section = document.split(marker, 1)[1]
    match = re.search(r"```yaml\n(.*?)\n```", section, re.DOTALL)
    assert match, f"missing YAML block after {marker}"
    parsed = yaml.safe_load(match.group(1))
    assert isinstance(parsed, dict)
    return parsed


def _fenced_commands(document: str, marker: str) -> list[list[str]]:
    section = document.split(marker, 1)[1]
    match = re.search(r"```(?:bash|console)\n(.*?)\n```", section, re.DOTALL)
    assert match, f"missing shell block after {marker}"
    commands: list[list[str]] = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        commands.append(shlex.split(line))
    return commands


def _generator_scripts(command_text: str) -> list[str]:
    return re.findall(r"scripts/(?:build|generate)_[a-z_]+\.py", command_text)


def test_readme_keeps_live_test_badge_without_fixed_numeric_count():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "actions/workflows/test.yml/badge.svg" in readme
    assert not re.search(r"shields\.io/badge/tests-[0-9]", readme)


def test_canonical_json_reference_matches_representative_runtime_serialization():
    document = (REPO_ROOT / "docs" / "JSON_OUTPUT.md").read_text(encoding="utf-8")
    schema_match = re.search(r"Schema version:\s*`(\d+)`", document)
    assert schema_match
    assert int(schema_match.group(1)) == REPORT_SCHEMA_VERSION

    report = build_demo_report()
    representative = report_to_dict(report)
    nullable_variant = report_to_dict(
        replace(
            report,
            components_skipped_reason=None,
            distribution=None,
        )
    )
    runtime_paths: defaultdict[str, set[str]] = defaultdict(set)
    _collect_json_paths(representative, "", runtime_paths)
    _collect_json_paths(nullable_variant, "", runtime_paths)

    rows = _markdown_table(document, "## Complete serialized shape")
    documented = {
        row["Path"].strip("`"): set(row["JSON type"].strip("`").split(" or ")) for row in rows
    }
    assert documented == dict(runtime_paths)
    assert all(row["Required key"] == "yes" for row in rows)

    stable_rows = _markdown_table(document, "## Stable consumer fields")
    stable_paths = {
        row["Purpose"]: set(re.findall(r"`([^`]+)`", row["Paths"])) for row in stable_rows
    }
    assert stable_paths["Schema identity"] == {"schema_version"}
    assert stable_paths["Evaluated instance identity"] == {"instance_id", "instance_name"}
    assert stable_paths["Source identity"] == {
        "adapter.platform",
        "adapter.tool",
        "adapter.version",
    }
    assert stable_paths["Rubric identity"] == {"rubric.pack", "rubric.version"}
    assert stable_paths["Grader identity"] == {"tool_version", "tool_url"}
    assert stable_paths["Grade result"] == {"grade", "overall_pct", "categories[]"}

    block_rows = _markdown_table(document, "## Finding body variants")
    variants = {row["`kind`"].strip("`"): row["Content field or fields"] for row in block_rows}
    assert variants == {
        "paragraph": "`html`",
        "section": "`label`, optionally `body_html`",
        "components": "`items`",
        "code": "`text`",
    }
    assert {
        block["kind"] for finding in representative["findings"] for block in finding["body"]
    } == {
        "paragraph",
        "section",
        "components",
        "code",
    }

    assert re.search(r"retained throughout the\s+`1\.2\.x` release line", document)
    assert "`impact_pts`" in document
    assert "`priority_weight`" in document


def test_json_reference_defines_html_string_trust_after_serialization():
    document = (REPO_ROOT / "docs" / "JSON_OUTPUT.md").read_text(encoding="utf-8")
    rows = _markdown_table(document, "## HTML-bearing strings and trust")
    by_path = {row["Path"]: row for row in rows}

    assert set(by_path) == {
        "`tldr_html`",
        "`methodology.paragraphs[]`",
        "`findings[].body[].html` / `body_html`",
        "`distribution.charts[].svg`",
    }
    for row in rows:
        assert "ordinary JSON string" in row["JSON consumer rule"]
    assert by_path["`findings[].body[].html` / `body_html`"]["Renderer source"] == "untrusted text"
    assert "sanitize" in document.lower()


def test_security_is_the_five_surface_privacy_authority():
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    rows = _markdown_table(security, "## Report-sharing privacy matrix")
    assert [row["Surface"] for row in rows] == [
        "HTML report",
        "Uncapped JSON",
        "CI logs",
        "GitHub Actions artifacts",
        "Claude conversation context",
    ]
    required_columns = {
        "Retained data",
        "Minimization / review",
        "Access audience",
        "Leaves the local machine?",
        "Retention effect",
    }
    for row in rows:
        assert required_columns < row.keys()
        assert all(len(row[column]) >= 12 for column in required_columns)

    artifact = rows[3]
    assert "opt in" in artifact["Minimization / review"].lower()
    assert "not confidential" in artifact["Access audience"].lower()
    assert "seven days" in artifact["Retention effect"].lower()
    assert "not access control" in artifact["Retention effect"].lower()

    ci = (REPO_ROOT / "docs" / "CI_INTEGRATION.md").read_text(encoding="utf-8")
    skill_readme = (REPO_ROOT / "skills" / "sdr-grader" / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "sdr-grader" / "SKILL.md").read_text(encoding="utf-8")
    assert "../SECURITY.md" in ci
    assert "JSON_OUTPUT.md" in ci
    for document in (skill_readme, skill):
        assert "blob/v1.2.2/docs/JSON_OUTPUT.md" in document
        assert "blob/v1.2.2/SECURITY.md#report-sharing-privacy-matrix" in document


def test_public_ci_example_uses_reviewed_pins_and_opt_in_artifacts():
    document = (REPO_ROOT / "docs" / "CI_INTEGRATION.md").read_text(encoding="utf-8")
    workflow = _fenced_yaml(document, "## GitHub Actions example")
    assert workflow["permissions"] == {"contents": "read"}

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    grade = jobs["grade"]
    assert isinstance(grade, dict)
    steps = grade["steps"]
    assert isinstance(steps, list)
    by_name = {step.get("name", "checkout"): step for step in steps}

    repo_workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    reviewed_pins = dict(
        re.findall(
            r"uses:\s+((?:actions/checkout|astral-sh/setup-uv|actions/upload-artifact))@([0-9a-f]{40})",
            repo_workflow,
        )
    )
    public_uses = {
        step["uses"].split("@", 1)[0]: step["uses"].split("@", 1)[1]
        for step in steps
        if "uses" in step
    }
    assert public_uses == reviewed_pins

    checkout = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["persist-credentials"] is False
    assert by_name["Install uv"]["with"]["version"] == "0.11.16"
    assert by_name["Install sdr-grader"]["run"] == "uv tool install sdr-grader==1.2.2"

    grader_command = by_name["Run grader"]["run"].replace("\\\n", " ")
    assert "sdr-grader path/to/snapshot.json" in grader_command
    assert "--output reports/sdr-grade.html" in grader_command
    assert "--json reports/sdr-grade.json" in grader_command
    assert "--quiet" in grader_command
    assert "uv tool run" not in grader_command

    upload = by_name["Upload report"]
    assert "always()" in upload["if"]
    assert "vars.SDR_GRADER_UPLOAD_REPORTS == 'true'" in upload["if"]
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 7
    assert upload["with"]["path"] == "reports/sdr-grade.html\nreports/sdr-grade.json\n"
    assert "if: always()" not in document
    assert "retention is temporal cleanup" in document.lower()


def test_leaderboard_workflow_uses_portable_outputs_and_qualifies_repo_helper():
    document = (REPO_ROOT / "docs" / "LEADERBOARDS.md").read_text(encoding="utf-8")

    assert "/dev/null" not in document
    commands = _fenced_commands(document, "## Installed grading workflow")
    grader_commands = [command for command in commands if command[0] == "sdr-grader"]
    assert grader_commands
    for command in grader_commands:
        output = command[command.index("--output") + 1]
        json_output = command[command.index("--json") + 1]
        assert Path(output).suffix == ".html"
        assert Path(json_output).suffix == ".json"
        assert not Path(output).is_absolute()
        assert not Path(json_output).is_absolute()

    source_commands = _fenced_commands(document, "## Source-checkout aggregation")
    assert any("scripts/aggregate_distributions.py" in command for command in source_commands)
    source_section = document.split("## Source-checkout aggregation", 1)[1]
    assert "repository root" in source_section.split("##", 1)[0].lower()


def test_contributor_only_paths_are_labeled_as_source_checkout_workflows():
    documents = {
        "CUSTOMIZATION.md": "src/sdr_grader/rules/packs/strict",
        "RUBRIC_FORMAT.md": "src/sdr_grader/rules/packs/strict",
        "ADAPTER_GUIDE.md": "tests/test_adapters_cja.py",
        "CHECK_FUNCTION_GUIDE.md": "tests/test_rules_<category>.py",
    }
    for filename, repo_only_path in documents.items():
        document = (REPO_ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert repo_only_path in document
        assert "source-checkout" in document.lower()
        assert "repository root" in document.lower()


def test_adapter_guide_matches_model_and_platform_extension_surfaces():
    document = (REPO_ROOT / "docs" / "ADAPTER_GUIDE.md").read_text(encoding="utf-8")

    component_rows = _markdown_table(document, "## Normalized `Component` vocabulary")
    assert {row["Field"].strip("`") for row in component_rows} == {
        field.name for field in fields(Component)
    }

    checklist = _markdown_table(document, "## Platform integration checklist")
    by_surface = {row["Surface"]: row for row in checklist}
    assert set(by_surface) == {
        "Detection",
        "Dispatch",
        "Normalization",
        "Validation",
        "CLI choices",
        "Labels",
        "Rule applicability",
    }
    assert "detect.py" in by_surface["Detection"]["Authority"]
    assert "adapt.py" in by_surface["Dispatch"]["Authority"]
    assert "models.py" in by_surface["Normalization"]["Authority"]
    assert "cli/main.py" in by_surface["CLI choices"]["Authority"]
    assert "rubric.py" in by_surface["Rule applicability"]["Authority"]
    platform_action = next(
        action for action in _build_parser()._actions if action.dest == "platform"
    )
    cli_choices = set(platform_action.choices or ())
    assert cli_choices == VALID_PLATFORMS
    assert set(_PLATFORM_NOUN) == set(_PLATFORM_TOOL) == set(PLATFORM_NOUN) == VALID_PLATFORMS
    for platform in cli_choices:
        assert f"`{platform}`" in by_surface["CLI choices"]["Required change"]

    boundary = _markdown_table(document, "## Rule input boundary")
    by_source = {row["Source"]: row for row in boundary}
    assert by_source["`Implementation.raw`"]["Rule contract"] == "No"
    assert by_source["Normalized model fields"]["Rule contract"] == "Yes"
    assert by_source["Documented supplementary input"]["Rule contract"] == "Yes"
    assert re.search(
        r"empty\s+effective\s+rule\s+inventory.*A\s*/\s*100",
        document,
        re.I | re.S,
    )


def test_check_guide_documents_the_renderer_trust_boundary():
    document = (REPO_ROOT / "docs" / "CHECK_FUNCTION_GUIDE.md").read_text(encoding="utf-8")
    rows = _markdown_table(document, "## Renderer trust boundary")
    by_value = {row["Value"]: row for row in rows}

    ordinary = by_value["Ordinary `str`"]
    assert "escaped" in ordinary["Renderer behavior"].lower()
    trusted = by_value["`Markup`"]
    assert "maintainer" in trusted["Allowed producer"].lower()
    assert "static" in trusted["Allowed producer"].lower()
    assert "reviewed" in trusted["Allowed producer"].lower()


def test_platform_coverage_matches_bundled_pack_applicability():
    document = (REPO_ROOT / "docs" / "PLATFORM_COVERAGE.md").read_text(encoding="utf-8")
    rows = _markdown_table(document, "## Bundled coverage inventory")
    documented = {
        row["Platform"].lower(): {
            "count": int(row["Applicable rules"]),
            "excluded": set(re.findall(r"[A-Z]+-\d+", row["Excluded IDs"])),
        }
        for row in rows
    }

    for pack_name in ("strict", "pragmatic"):
        rubric = load_rubric(REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / pack_name)
        for platform in VALID_PLATFORMS:
            applicable = {rule.id for rule in rubric.rules if platform in rule.platforms}
            excluded = {rule.id for rule in rubric.rules} - applicable
            assert applicable
            assert documented[platform] == {"count": len(applicable), "excluded": excluded}


def test_contributor_regeneration_sequence_matches_examples_drift_ci():
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["examples-drift"]["steps"]
    ci_scripts = [
        script for step in steps for script in _generator_scripts(str(step.get("run", "")))
    ]

    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    contributor_commands = _fenced_commands(contributing, "## Regenerating fixtures and examples")
    contributor_scripts = [
        script
        for command in contributor_commands
        for script in _generator_scripts(" ".join(command))
    ]
    assert contributor_scripts == ci_scripts
    assert len([script for script in ci_scripts if "/build_" in script]) == 1
    assert len([script for script in ci_scripts if "/generate_" in script]) == 3

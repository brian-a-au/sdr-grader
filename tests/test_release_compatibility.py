from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_release_compatibility.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_release_compatibility", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compatibility_baseline_and_normalization_are_explicit_and_narrow():
    module = _load_module()
    report = {
        "tool_version": "1.2.2",
        "overall_pct": 87,
        "categories": [{"name": "schema", "pct": 91}],
        "findings": [{"rule_id": "SCH-001"}],
        "methodology": {"paragraphs": ["new copy"], "other": "preserved"},
        "distribution": {"charts": [{"label": "new copy", "svg": "preserved"}]},
    }

    normalized = module._normalize_report(report)

    assert module.BASELINE_TAG == "v1.2.2"
    assert module.BASELINE_COMMIT == "1978eb6d6e8d865e66f2dd464624db9a377417de"
    assert module.UV_VERSION == "0.11.16"
    assert module.NORMALIZED_COPY_FIELDS == (
        "methodology.paragraphs",
        "distribution.charts[].label",
    )
    assert module.FIXTURE_FAIL_BELOW_A_EXITS == {
        "cja_snapshot_clean.json": 0,
        "cja_snapshot_messy.json": 2,
        "aa_snapshot_clean.json": 0,
        "aa_snapshot_messy.json": 2,
    }
    assert normalized == {
        "tool_version": "<normalized-version>",
        "overall_pct": 87,
        "categories": [{"name": "schema", "pct": 91}],
        "findings": [{"rule_id": "SCH-001"}],
        "methodology": {"paragraphs": "<normalized-copy>", "other": "preserved"},
        "distribution": {"charts": [{"label": "<normalized-copy>", "svg": "preserved"}]},
    }
    assert report["tool_version"] == "1.2.2"


def test_compatibility_fetches_only_the_public_baseline_tag(monkeypatch):
    module = _load_module()
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        stdout = f"{module.BASELINE_COMMIT}\n" if command[:2] == ["git", "rev-parse"] else ""
        return module.subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(module, "_run", fake_run)

    module._fetch_and_verify_baseline(REPO_ROOT, module._clean_environment())

    fetch = commands[0]
    assert fetch == [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "core.askPass=",
        "fetch",
        "--no-tags",
        "--force",
        module.PUBLIC_REMOTE,
        "+refs/tags/v1.2.2:refs/tags/v1.2.2",
    ]
    assert "--tags" not in fetch


def test_compatibility_allows_dev_only_lock_drift():
    module = _load_module()
    assert not hasattr(module, "_verify_lock_identity")


def _reference_finding(rule_id, items, paragraph="old copy"):
    noun = "broken references" if rule_id == "SCH-002" else "broken calculated metric references"
    return {
        "id": rule_id,
        "title": f"{len(items)} {noun}",
        "body": [
            {"kind": "paragraph", "html": paragraph},
            {"kind": "components", "items": items},
        ],
    }


def test_approved_delta_removes_only_exact_cja_core_reference_items():
    module = _load_module()
    visits = "calculatedMetrics/cm -> metrics/visits"
    missing = "calculatedMetrics/cm -> metrics/visits_custom"
    nested = "calculatedMetrics/cm -> nested/metrics/visits"
    baseline = {
        "fixtures": {
            "cja_snapshot_messy.json": {
                "report": {
                    "schema_version": 1,
                    "adapter": {"platform": "CJA"},
                    "overall_pct": 47,
                    "categories": [{"name": "schema", "pct": 71}],
                    "findings": [_reference_finding("CALC-002", [visits, missing, nested])],
                }
            }
        }
    }

    expected = module._expected_candidate_from_baseline(baseline)
    finding = expected["fixtures"]["cja_snapshot_messy.json"]["report"]["findings"][0]

    assert finding["title"] == "2 unresolved calculated metric references"
    assert finding["body"][1]["items"] == [missing, nested]
    assert "does not prove the live implementation is broken" in finding["body"][0]["html"]
    assert baseline["fixtures"]["cja_snapshot_messy.json"]["report"]["findings"][0]["body"][1][
        "items"
    ] == [visits, missing, nested]


def test_approved_delta_keeps_non_cja_items_and_normalizes_only_copy():
    module = _load_module()
    visits = "calculatedMetrics/cm -> metrics/visits"
    baseline = {
        "report": {
            "schema_version": 1,
            "adapter": {"platform": "AA"},
            "overall_pct": 47,
            "categories": [],
            "findings": [_reference_finding("CALC-002", [visits])],
        }
    }

    expected = module._expected_candidate_from_baseline(baseline)
    finding = expected["report"]["findings"][0]

    assert finding["title"] == "1 unresolved calculated metric reference"
    assert finding["body"][1]["items"] == [visits]
    assert finding["body"][0]["html"] != "old copy"


def test_verifier_rejects_other_payload_drift(tmp_path, monkeypatch):
    module = _load_module()
    baseline = {
        "report": {
            "schema_version": 1,
            "adapter": {"platform": "CJA"},
            "overall_pct": 47,
            "categories": [{"name": "schema", "pct": 71}],
            "findings": [_reference_finding("SCH-002", ["segment/s -> missing metrics/deleted"])],
        }
    }
    expected = module._expected_candidate_from_baseline(baseline)

    wrong_item = json.loads(json.dumps(expected))
    wrong_item["report"]["findings"][0]["body"][1]["items"] = []
    wrong_count = json.loads(json.dumps(expected))
    wrong_count["report"]["findings"][0]["title"] = "2 broken references"
    score_drift = json.loads(json.dumps(expected))
    score_drift["report"]["overall_pct"] = 48

    monkeypatch.setattr(module, "_verify_uv", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_fetch_and_verify_baseline", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_readme_arguments", lambda *args, **kwargs: ["sdr-grader"])
    monkeypatch.setattr(module, "_extract_baseline", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_sync_environment", lambda *args, **kwargs: {})

    for candidate in (wrong_item, wrong_count, score_drift):
        results = iter((candidate, baseline))
        monkeypatch.setattr(module, "_run_grades", lambda **kwargs: next(results))
        with pytest.raises(module.CompatibilityError, match="beyond the approved"):
            module.verify_compatibility(tmp_path)


def test_readme_command_contract_replaces_only_argv_zero(tmp_path):
    module = _load_module()
    (tmp_path / "README.md").write_text(
        f"```bash\n{module.README_COMMAND}\n```\n",
        encoding="utf-8",
    )

    arguments = module._readme_arguments(tmp_path)

    assert arguments == [
        "sdr-grader",
        "cja_snapshot_clean.json",
        "--output",
        "grade.html",
        "--json",
        "grade.json",
        "--quiet",
    ]
    replacement = ["/isolated/bin/sdr-grader", *arguments[1:]]
    assert replacement[1:] == arguments[1:]


def test_grade_matrix_exercises_every_fixture_and_threshold_exit(tmp_path, monkeypatch):
    module = _load_module()
    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    for filename in module.FIXTURE_FAIL_BELOW_A_EXITS:
        payload = {}
        if filename.startswith("cja_"):
            identity = "messy" if "messy" in filename else "clean"
            payload = {
                "data_view": {
                    "data_view_id": identity,
                    "data_view_name": identity,
                },
                "metadata": {
                    "Data View ID": identity,
                    "Data View Name": identity,
                },
            }
        (fixture_root / filename).write_text(json.dumps(payload), encoding="utf-8")

    observed_console_commands: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd, env=None, capture=False):
        if command[0].endswith("sdr-grader"):
            observed_console_commands.append((command, Path(cwd)))
            json_path = Path(cwd) / command[command.index("--json") + 1]
            html_path = Path(cwd) / command[command.index("--output") + 1]
            payload = {
                "schema_version": 1,
                "tool_version": "1.2.2",
                "overall_pct": 47,
                "findings": [],
                "categories": [],
                "methodology": {"paragraphs": []},
                "distribution": None,
            }
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            html_path.write_text("<!doctype html>", encoding="utf-8")
            threshold = "--fail-below" in command
            messy = "messy" in command[1]
            returncode = 2 if threshold and messy else 0
            return module.subprocess.CompletedProcess(command, returncode, "", "")
        if "build_trend_report" in command[-2]:
            reports = [
                {
                    "schema_version": 1,
                    "tool_version": "1.2.2",
                    "overall_pct": score,
                    "findings": [],
                    "categories": [],
                    "methodology": {"paragraphs": []},
                    "distribution": None,
                }
                for score in (100, 47)
            ]
            trend = {
                "schema_version": 1,
                "instance_id": "trend",
                "platform": "cja",
                "points": [
                    {"timestamp": f"2026-01-0{index}", "report": report}
                    for index, report in enumerate(reports, start=1)
                ],
            }
            return module.subprocess.CompletedProcess(command, 0, json.dumps(trend), "")
        return module.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "_run", fake_run)

    results = module._run_grades(
        environment_root=tmp_path / "env",
        environment={},
        work_root=tmp_path / "output",
        fixture_root=fixture_root,
        readme_arguments=module.README_COMMAND.split(),
    )

    matrix = results["fixtures"]
    assert set(matrix) == set(module.FIXTURE_FAIL_BELOW_A_EXITS)
    for filename, expected_exit in module.FIXTURE_FAIL_BELOW_A_EXITS.items():
        assert matrix[filename]["normal_exit"] == 0
        assert matrix[filename]["fail_below_a_exit"] == expected_exit
    fixture_commands = [
        command for command, cwd in observed_console_commands if "fixture-matrix" in cwd.parts
    ]
    assert len(fixture_commands) == 8
    assert sum("--fail-below" in command for command in fixture_commands) == 4


@pytest.mark.parametrize("rule_id", ["SCH-002", "CALC-002"])
def test_exact_verify_first_copy_applies_to_finding_and_top_remediation(rule_id):
    module = _load_module()
    old_copy = module.BASELINE_REFERENCE_REMEDIATIONS[rule_id]
    item = (
        "segment/s -> missing metrics/deleted" if rule_id == "SCH-002" else "cm -> metrics/deleted"
    )
    finding = _reference_finding(rule_id, [item])
    finding["severity"] = "high"
    finding["body"].append({"kind": "section", "label": "How to remediate", "body_html": old_copy})
    baseline = {
        "report": {
            "schema_version": 1,
            "adapter": {"platform": "CJA"},
            "overall_pct": 47,
            "categories": [{"name": "schema", "pct": 71}],
            "findings": [finding],
            "remediations": [
                {"text": old_copy, "refs": [rule_id], "priority_weight": 5, "impact_pts": 5}
            ],
        }
    }
    expected = module._expected_candidate_from_baseline(baseline)
    report = expected["report"]
    assert report["findings"][0]["body"][-1]["body_html"] == module.APPROVED_REFERENCE_REMEDIATION
    assert report["remediations"][0]["text"] == module.APPROVED_REFERENCE_REMEDIATION
    module._verify_expected_candidate(expected, baseline)

    for target, key, wrong_value in [
        (report, "overall_pct", 48),
        (report["categories"][0], "pct", 72),
        (report["findings"][0], "severity", "low"),
        (report["findings"][0], "title", "2 unresolved references"),
        (report["findings"][0]["body"][-1], "body_html", "Delete it immediately."),
        (report["remediations"][0], "text", "Delete it immediately."),
        (report["remediations"][0], "priority_weight", 1),
    ]:
        original = target[key]
        target[key] = wrong_value
        with pytest.raises(module.CompatibilityError, match="beyond the approved"):
            module._verify_expected_candidate(expected, baseline)
        target[key] = original


def test_remediation_copy_does_not_rewrite_other_fields_rules_or_unreviewed_text():
    module = _load_module()
    old_copy = module.BASELINE_REFERENCE_REMEDIATIONS["SCH-002"]
    finding = _reference_finding("SCH-002", ["segment/s -> missing metrics/deleted"])
    finding["body"].extend(
        [
            {"kind": "section", "label": "How to remediate", "body_html": "unreviewed copy"},
            {"kind": "section", "label": "Other label", "body_html": old_copy},
        ]
    )
    baseline = {
        "schema_version": 1,
        "categories": [],
        "findings": [finding],
        "remediations": [
            {"refs": ["SCH-002"], "text": "unreviewed copy"},
            {"refs": ["SCH-001"], "text": old_copy},
            {"refs": ["SCH-002", "SCH-001"], "text": old_copy},
        ],
    }
    expected = module._expected_candidate_from_baseline(baseline)
    assert expected["findings"][0]["body"][-2:] == finding["body"][-2:]
    assert expected["remediations"] == baseline["remediations"]


def test_repeated_formula_copy_delta_is_bound_to_exact_cja_item():
    module = _load_module()
    baseline_item = module.BASELINE_REPEATED_FORMULA_ITEM
    other_item = baseline_item.replace("cm_rpv_marketing", "cm_other")
    for platform in ("CJA", "AA"):
        baseline = {
            "schema_version": 1,
            "adapter": {"platform": platform},
            "categories": [],
            "findings": [
                {
                    "id": "CALC-015",
                    "body": [{"kind": "components", "items": [baseline_item, other_item]}],
                },
                {"id": "CALC-014", "body": [{"kind": "components", "items": [baseline_item]}]},
            ],
        }
        expected = module._expected_candidate_from_baseline(baseline)
        assert expected["findings"][0]["body"][0]["items"] == [
            module.APPROVED_REPEATED_FORMULA_ITEM if platform == "CJA" else baseline_item,
            other_item,
        ]
        assert expected["findings"][1] == baseline["findings"][1]
        expected["findings"][0]["body"][0]["items"][0] = "'Revenue / Visits': cm_wrong"
        with pytest.raises(module.CompatibilityError):
            module._verify_expected_candidate(expected, baseline)


@pytest.mark.parametrize(
    ("platform", "instance_id", "old_count", "new_count"),
    [
        ("AA", "clean.prod", 19, 32),
        ("AA", "messy.prod", 75, 79),
        ("CJA", "dv_clean_prod_web", 40, 53),
        ("CJA", "dv_messy_prod_web", 487, 542),
        ("CJA", "dv_messy_prod_web", 40, 53),
    ],
)
def test_exact_public_component_counts_and_summary_are_corrected(
    platform, instance_id, old_count, new_count
):
    module = _load_module()
    noun = "data view" if platform == "CJA" else "report suite"
    baseline = {
        "report": {
            "schema_version": 1,
            "findings": [],
            "categories": [],
            "overall_pct": 47,
            "adapter": {"platform": platform},
            "instance_id": instance_id,
            "components_evaluated": old_count,
            "tldr_html": f"Preserve prefix. The grader evaluated {old_count} components in this {noun} using the rubric. Preserve suffix.",
        }
    }
    expected = module._expected_candidate_from_baseline(baseline)
    report = expected["report"]
    assert report["components_evaluated"] == new_count
    assert report["tldr_html"] == baseline["report"]["tldr_html"].replace(
        f"evaluated {old_count} components", f"evaluated {new_count} components"
    )
    module._verify_expected_candidate(expected, baseline)
    for key, value in [
        ("components_evaluated", new_count + 1),
        ("tldr_html", "unapproved summary"),
        ("overall_pct", 48),
    ]:
        original = report[key]
        report[key] = value
        with pytest.raises(module.CompatibilityError):
            module._verify_expected_candidate(expected, baseline)
        report[key] = original


@pytest.mark.parametrize(
    ("platform", "instance_id", "count"),
    [
        ("AA", "other.prod", 19),
        ("CJA", "clean.prod", 19),
        ("AA", "clean.prod", 20),
    ],
)
def test_component_count_delta_does_not_apply_to_other_inventory_or_identity(
    platform, instance_id, count
):
    module = _load_module()
    baseline = {
        "schema_version": 1,
        "findings": [],
        "categories": [],
        "adapter": {"platform": platform},
        "instance_id": instance_id,
        "components_evaluated": count,
        "tldr_html": "unchanged",
    }
    assert module._expected_candidate_from_baseline(baseline) == baseline


@pytest.mark.parametrize("rule_id,separator", [("SCH-002", " -> missing "), ("CALC-002", " -> ")])
@pytest.mark.parametrize("platform", ["CJA", "AA"])
def test_reference_order_delta_sorts_only_within_cja_consumer_groups(rule_id, separator, platform):
    module = _load_module()
    # Consumer order is intentionally nonalphabetical; repeated items must survive.
    old_items = [f"cm_z{separator}metrics/z", f"cm_z{separator}metrics/a",
                 f"cm_a{separator}metrics/z", f"cm_a{separator}metrics/a",
                 f"cm_a{separator}metrics/a"]
    sorted_items = [old_items[1], old_items[0], old_items[3], old_items[4], old_items[2]]
    baseline = {
        "schema_version": 1, "adapter": {"platform": platform}, "categories": [],
        "overall_pct": 47, "findings": [_reference_finding(rule_id, old_items)],
    }
    expected = module._expected_candidate_from_baseline(baseline)
    wanted = sorted_items if platform == "CJA" else old_items
    assert expected["findings"][0]["body"][1]["items"] == wanted
    assert baseline["findings"][0]["body"][1]["items"] == old_items
    module._verify_expected_candidate(expected, baseline)
    for bad_items in (wanted[:-1], wanted + [wanted[0]],
                      [wanted[0].replace("metrics/", "variables/"), *wanted[1:]],
                      wanted[2:] + wanted[:2]):
        candidate = json.loads(json.dumps(expected))
        candidate["findings"][0]["body"][1]["items"] = bad_items
        with pytest.raises(module.CompatibilityError):
            module._verify_expected_candidate(candidate, baseline)
    expected["overall_pct"] += 1
    with pytest.raises(module.CompatibilityError):
        module._verify_expected_candidate(expected, baseline)


def test_correctness_baseline_is_separate_and_immutable():
    module = _load_module()
    assert module.CORRECTNESS_BASELINE_TAG == 'v1.2.9'
    assert module.CORRECTNESS_BASELINE_COMMIT == '9687fcc66622d454cc121cd49daa319c0c01a939'
    assert module.BASELINE_TAG == 'v1.2.2'


@pytest.mark.parametrize('field,value', [('exit', 2), ('overall_pct', 99), ('findings', [])])
def test_correctness_comparator_rejects_unexpected_drift(field, value):
    module = _load_module()
    baseline = {'exit': 0, 'overall_pct': 100, 'findings': [{'id': 'GOV-001'}]}
    candidate = {'exit': 0, 'overall_pct': 100, 'findings': [{'id': 'GOV-003'}]}
    contract = {'baseline': baseline, 'candidate': candidate,
                'deltas': module._exact_deltas(baseline, candidate)}
    module._verify_correctness_case('proof', baseline, candidate, contract)
    changed = json.loads(json.dumps(candidate))
    changed[field] = value
    with pytest.raises(module.CompatibilityError, match='proof'):
        module._verify_correctness_case('proof', baseline, changed, contract)
    with pytest.raises(module.CompatibilityError, match='baseline'):
        module._verify_correctness_case('proof', changed, candidate, contract)


def test_correctness_normalizes_only_package_version():
    module = _load_module()
    payload = {'tool_version': '1.3.0', 'methodology': {'paragraphs': ['keep']},
               'findings': [{'body': ['keep']}], 'overall_pct': 100}
    normalized = module._correctness_payload(payload)
    assert normalized == {**payload, 'tool_version': '<package-version>'}
    assert payload['tool_version'] == '1.3.0'


def test_correctness_fetch_rejects_moved_baseline(monkeypatch):
    module = _load_module()
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return module.subprocess.CompletedProcess(command, 0, 'wrong-sha\n', '')
    monkeypatch.setattr(module, '_run', run)
    with pytest.raises(module.CompatibilityError, match='v1.2.9 peeled'):
        module._fetch_and_verify_baseline(REPO_ROOT, {}, tag=module.CORRECTNESS_BASELINE_TAG,
                                          commit=module.CORRECTNESS_BASELINE_COMMIT)
    assert commands[0][-1] == '+refs/tags/v1.2.9:refs/tags/v1.2.9'


@pytest.mark.parametrize('exit_code,diagnostic', [(1, 'error: metadata.sdr_doc_present: invalid'),
                                                 (3, 'rubric error: GOV-001.params: invalid')])
def test_correctness_errors_are_typed_and_publish_no_reports(tmp_path, monkeypatch, exit_code, diagnostic):
    module = _load_module()
    def run(command, **kwargs):
        return module.subprocess.CompletedProcess(command, exit_code, '', diagnostic)
    monkeypatch.setattr(module, '_run', run)
    args = dict(console=Path('sdr-grader'), python=Path('python'), environment={},
                fixture_root=tmp_path, case={'name':'invalid','files':{'input.json':{}}})
    result = module._run_correctness_case(case_root=tmp_path/'ok', **args)
    assert result['kind'] == ('invalid-input' if exit_code == 1 else 'rubric-error')
    assert result['diagnostic'] == diagnostic
    assert not result['html_present'] and not result['json_present']
    def leaked_report(command, **kwargs):
        (kwargs['cwd']/'grade.html').write_text('bad success')
        return run(command, **kwargs)
    monkeypatch.setattr(module, '_run', leaked_report)
    with pytest.raises(module.CompatibilityError, match='error published success artifacts'):
        module._run_correctness_case(case_root=tmp_path/'bad', **args)


def test_correctness_rejects_traceback_as_input_failure(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, '_run', lambda *a, **k:
        module.subprocess.CompletedProcess(a[0], 1, '', 'Traceback: crashed'))
    with pytest.raises(module.CompatibilityError, match='untyped failure'):
        module._run_correctness_case(console=Path('sdr-grader'), python=Path('python'),
            environment={}, case_root=tmp_path/'case', fixture_root=tmp_path,
            case={'name':'crash','files':{'input.json':{}}})


def test_reviewed_correctness_matrix_has_complete_exact_contract():
    module = _load_module()
    root = REPO_ROOT / 'tests/fixtures/correctness_1_3'
    cases = json.loads((root/'cases.json').read_text())
    expected = json.loads((root/'expectations.json').read_text())
    assert expected['baseline_commit'] == module.CORRECTNESS_BASELINE_COMMIT
    assert expected['normalization'] == 'tool_version only'
    assert len({case['name'] for case in cases}) == len(cases)
    assert {case['name'] for case in cases} == expected['cases'].keys()
    for name, contract in expected['cases'].items():
        module._verify_correctness_case(name, contract['baseline'], contract['candidate'], contract)
    for pack in ('strict', 'pragmatic'):
        for platform in ('cja', 'aa'):
            for quality in ('clean', 'messy'):
                assert expected['cases'][f'{platform}-{quality}-{pack}']['deltas'] == []
        assert expected['cases'][f'attribution-decay-{pack}']['candidate']['report']['overall_pct'] == 100
        assert expected['cases'][f'chronology-at-{pack}']['baseline']['exit'] == 1
    assert {c['candidate']['kind'] for c in expected['cases'].values()} == {
        'report', 'invalid-input', 'rubric-error'}


def test_correctness_rejects_repeated_html_drift(tmp_path, monkeypatch):
    module = _load_module()
    calls = iter(['first HTML', 'different HTML'])
    def run(command, **kwargs):
        cwd = kwargs['cwd']
        (cwd/'grade.html').write_text(next(calls))
        (cwd/'grade.json').write_text(json.dumps({'schema_version':1,'overall_pct':100,
                                                 'findings':[],'categories':[]}))
        return module.subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(module, '_run', run)
    with pytest.raises(module.CompatibilityError, match='not deterministic'):
        module._run_correctness_case(console=Path('sdr-grader'), python=Path('python'),
            environment={}, case_root=tmp_path/'case', fixture_root=tmp_path,
            case={'name':'unstable','files':{'input.json':{}}})


@pytest.mark.parametrize('side', ['baseline', 'candidate'])
@pytest.mark.parametrize('path,value', [
    (('report', 'schema_version'), True),
    (('report', 'schema_version'), 1.0),
    (('exit',), False),
    (('html_present',), 1),
    (('json_present',), 1),
])
def test_real_correctness_oracle_rejects_json_type_substitution(side, path, value):
    module = _load_module()
    oracle = json.loads((REPO_ROOT / 'tests/fixtures/correctness_1_3/expectations.json').read_text())
    contract = oracle['cases']['cja-clean-strict']
    outcomes = json.loads(json.dumps(contract))
    target = outcomes[side]
    for key in path[:-1]:
        target = target[key]
    original = target[path[-1]]
    assert original == value and type(original) is not type(value)
    target[path[-1]] = value
    with pytest.raises(module.CompatibilityError, match='baseline' if side == 'baseline' else 'candidate'):
        module._verify_correctness_case('cja-clean-strict', outcomes['baseline'],
                                        outcomes['candidate'], contract)


@pytest.mark.parametrize('before,after', [(1, True), (0, False), (True, 1), (False, 0), (1, 1.0)])
def test_exact_deltas_retain_json_type_changes(before, after):
    module = _load_module()
    delta = module._exact_deltas({'nested': [before]}, {'nested': [after]})
    assert len(delta) == 1
    assert delta[0]['path'] == '/nested/0'
    assert type(delta[0]['before']) is type(before)
    assert type(delta[0]['after']) is type(after)


def test_real_correctness_oracle_rejects_type_drift_inside_recorded_deltas():
    module = _load_module()
    oracle = json.loads((REPO_ROOT / 'tests/fixtures/correctness_1_3/expectations.json').read_text())
    contract = oracle['cases']['boolean-cja-invalid-strict']
    assert contract['deltas'][0]['before']['exit'] == 0
    contract['deltas'][0]['before']['exit'] = False
    with pytest.raises(module.CompatibilityError, match='recorded exact deltas'):
        module._verify_correctness_case('boolean-cja-invalid-strict', contract['baseline'],
                                        contract['candidate'], contract)

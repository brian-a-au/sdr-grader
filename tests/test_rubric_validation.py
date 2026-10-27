"""Load-time validation of cross-check rule params (spec F8)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.rules.rubric import GradeBand, load_rubric, score_to_letter

_DEFAULT = object()
REPO_ROOT = Path(__file__).resolve().parent.parent


def _valid_meta() -> dict[str, object]:
    return {
        "pack": "test",
        "version": "1",
        "description": "test pack",
        "category_weights": {"naming_conventions": 1.0},
        "severity_weights": {"critical": 10, "high": 5, "medium": 3, "low": 1},
        "grade_scale": [{"min": 90, "grade": "A"}, {"min": 0, "grade": "F"}],
    }


def _valid_rule(**updates: object) -> dict[str, object]:
    rule: dict[str, object] = {
        "id": "NAME-T01",
        "name": "test rule",
        "severity": "low",
        "platforms": ["cja"],
        "check": "regex_match_id",
        "params": {},
    }
    rule.update(updates)
    return rule


def _write_structured_pack(
    tmp_path: Path,
    *,
    meta: object = _DEFAULT,
    category_content: object = _DEFAULT,
) -> Path:
    if meta is _DEFAULT:
        meta = _valid_meta()
    if category_content is _DEFAULT:
        category_content = {
            "category": "naming_conventions",
            "rules": [_valid_rule()],
        }
    (tmp_path / "_meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")
    (tmp_path / "naming.yaml").write_text(
        yaml.safe_dump(category_content, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


def test_invalid_regex_pattern_fails_at_load(tmp_path):
    category_content = {
        "category": "naming_conventions",
        "rules": [_valid_rule(params={"pattern": "["})],
    }
    pack = _write_structured_pack(tmp_path, category_content=category_content)
    with pytest.raises(RubricValidationError, match="pattern"):
        load_rubric(pack)


def test_unknown_target_fails_at_load(tmp_path):
    category_content = {
        "category": "naming_conventions",
        "rules": [_valid_rule(params={"targets": ["raw"]})],
    }
    pack = _write_structured_pack(tmp_path, category_content=category_content)
    with pytest.raises(RubricValidationError, match="targets"):
        load_rubric(pack)


def test_valid_params_still_load(tmp_path):
    category_content = {
        "category": "naming_conventions",
        "rules": [_valid_rule(params={"pattern": "^[a-z]+$"})],
    }
    pack = _write_structured_pack(tmp_path, category_content=category_content)
    rubric = load_rubric(pack)
    assert [r.id for r in rubric.rules] == ["NAME-T01"]
    assert rubric.categories_in_use == ["naming_conventions"]


_CHECK_FOR_KEY = {
    "threshold": "missing_descriptions",
    "min_consistency": "prefix_consistency",
    "min_similarity": "calc_near_duplicates",
    "max_complexity": "calc_complexity_threshold",
    "max_depth": "segment_nesting_depth",
    "cap_days": "persistence_lookback_exceeds_cap",
    "max_age_days": "snapshot_age",
}


def _load_with_params(tmp_path, params, check=None):
    check = check or _CHECK_FOR_KEY[next(iter(params))]
    category_content = {
        "category": "naming_conventions",
        "rules": [_valid_rule(check=check, params=params)],
    }
    return load_rubric(_write_structured_pack(tmp_path, category_content=category_content))


def test_float_param_rejects_integer_too_large_for_float(tmp_path):
    with pytest.raises(RubricValidationError) as exc:
        _load_with_params(tmp_path, {"threshold": 10**400})
    message = str(exc.value)
    assert "NAME-T01" in message
    assert "'threshold'" in message


def test_param_bounds_are_inclusive(tmp_path):
    _load_with_params(tmp_path, {"threshold": 0})
    _load_with_params(tmp_path, {"threshold": 1.00})
    _load_with_params(tmp_path, {"max_depth": 0})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_depth", "abc"),
        ("max_depth", float("nan")),
        ("max_depth", 2.5),
        ("max_depth", 5.0),
        ("max_depth", True),
        ("max_depth", -1),
        ("max_depth", 10**400),
        ("threshold", [1]),
        ("threshold", float("nan")),
        ("threshold", float("inf")),
        ("threshold", 1.5),
        ("threshold", -0.1),
        ("min_consistency", 1.5),
        ("min_similarity", -0.1),
        ("max_complexity", -1),
        ("cap_days", 2.5),
        ("max_age_days", True),
    ],
)
def test_invalid_numeric_params_rejected(tmp_path, key, value):
    with pytest.raises(RubricValidationError) as exc:
        _load_with_params(tmp_path, {key: value})
    message = str(exc.value)
    assert "NAME-T01" in message
    assert f"'{key}'" in message
    assert "must be" in message
    assert "'abc'" not in message


def test_colliding_category_weight_keys_fail_at_load(tmp_path):
    """Spec F39: keys that normalize to one rendered slug are rejected."""
    meta = _valid_meta()
    meta["category_weights"] = {
        "naming_conventions": 0.5,
        "Naming Conventions": 0.5,
    }
    _write_structured_pack(tmp_path, meta=meta)
    with pytest.raises(
        RubricValidationError,
        match=r"naming_conventions.*Naming Conventions",
    ):
        load_rubric(tmp_path)


def test_missing_pack_directory_has_contextual_error(tmp_path):
    missing = tmp_path / "missing-pack"

    with pytest.raises(RubricValidationError, match=str(missing)):
        load_rubric(missing)


def test_missing_meta_file_has_pack_context(tmp_path):
    with pytest.raises(RubricValidationError, match=r"missing required _meta\.yaml"):
        load_rubric(tmp_path)


@pytest.mark.parametrize("filename", ["_meta.yaml", "naming.yaml"])
def test_malformed_yaml_is_translated_to_contextual_validation_error(
    tmp_path,
    filename,
):
    _write_structured_pack(tmp_path)
    (tmp_path / filename).write_text("key: [unterminated\n", encoding="utf-8")

    with pytest.raises(
        RubricValidationError,
        match=rf"{re.escape(filename)}: invalid YAML syntax",
    ):
        load_rubric(tmp_path)


def test_rubric_yaml_read_failure_is_contextual(tmp_path, monkeypatch):
    _write_structured_pack(tmp_path)
    real_open = Path.open

    def fail_meta(path, *args, **kwargs):
        if path.name == "_meta.yaml":
            raise OSError("injected read failure")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_meta)

    with pytest.raises(
        RubricValidationError,
        match=r"_meta\.yaml: could not read YAML",
    ):
        load_rubric(tmp_path)


@pytest.mark.parametrize(
    ("meta", "message"),
    [
        ({}, "missing required string 'pack'"),
        (["not", "a", "mapping"], "must be a mapping, got list"),
        ({**_valid_meta(), "pack": 7}, "'pack' must be a string, got int"),
    ],
)
def test_meta_shape_and_required_strings_are_validated(tmp_path, meta, message):
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)


@pytest.mark.parametrize(
    ("category_weights", "message"),
    [
        (None, "missing 'category_weights' mapping"),
        ({"naming_conventions": "heavy"}, "is not numeric"),
        ({"naming_conventions": 0.75}, "must sum to 1.0; got 0.750000"),
    ],
)
def test_category_weights_reject_missing_nonnumeric_and_nonunit_values(
    tmp_path, category_weights, message
):
    meta = _valid_meta()
    meta["category_weights"] = category_weights
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_category_weights_reject_boolean_nonfinite_negative_and_oversized(
    tmp_path,
    value,
):
    meta = _valid_meta()
    meta["category_weights"] = {
        "naming_conventions": value,
        "other": 1.0,
    }
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(RubricValidationError, match="category_weights"):
        load_rubric(pack)


@pytest.mark.parametrize(
    ("severity_weights", "message"),
    [
        (None, "missing 'severity_weights' mapping"),
        (
            {"critical": 10, "high": 5, "medium": 3, "low": 1, "urgent": 20},
            "urgent.*not a valid severity",
        ),
        (
            {"critical": 10, "high": 5, "medium": 3, "low": "many"},
            "low.*must be an integer",
        ),
        ({"critical": 10}, "missing required keys.*high.*low.*medium"),
    ],
)
def test_severity_weights_reject_invalid_contracts(tmp_path, severity_weights, message):
    meta = _valid_meta()
    meta["severity_weights"] = severity_weights
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)


@pytest.mark.parametrize("value", [True, 1.5, 0, -1])
def test_severity_weights_require_positive_literal_integers(tmp_path, value):
    meta = _valid_meta()
    meta["severity_weights"] = {
        "critical": 10,
        "high": 5,
        "medium": 3,
        "low": value,
    }
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(
        RubricValidationError,
        match=r"severity_weights\['low'\].*positive integer",
    ):
        load_rubric(pack)


@pytest.mark.parametrize(
    ("grade_scale", "message"),
    [
        (None, "missing 'grade_scale' list"),
        (["A"], "entry must be a mapping"),
        ([{"min": 90}], "mapping with 'min' and 'grade'"),
        ([{"min": "high", "grade": "A"}], "non-numeric 'min'"),
        (
            [{"min": 90, "grade": "A"}, {"min": 90, "grade": "B"}],
            "strictly descending",
        ),
        (
            [{"min": 90, "grade": "A"}, {"min": 1, "grade": "F"}],
            "band starting at 0; lowest band starts at 1.0",
        ),
    ],
)
def test_grade_scale_rejects_malformed_and_invalid_boundaries(tmp_path, grade_scale, message):
    meta = _valid_meta()
    meta["grade_scale"] = grade_scale
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)


@pytest.mark.parametrize(
    "value",
    [True, float("nan"), float("inf"), -1, 101],
)
def test_grade_scale_rejects_boolean_nonfinite_and_out_of_range_values(
    tmp_path,
    value,
):
    meta = _valid_meta()
    meta["grade_scale"] = [
        {"min": 90, "grade": "A"},
        {"min": value, "grade": "F"},
    ]
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(
        RubricValidationError,
        match="grade_scale",
    ):
        load_rubric(pack)


def test_grade_scale_requires_nonempty_string_labels(tmp_path):
    meta = _valid_meta()
    meta["grade_scale"] = [
        {"min": 90, "grade": True},
        {"min": 0, "grade": "F"},
    ]
    pack = _write_structured_pack(tmp_path, meta=meta)

    with pytest.raises(
        RubricValidationError,
        match="grade_scale.*grade.*non-empty string",
    ):
        load_rubric(pack)


def test_score_to_letter_honors_exact_and_fallback_boundaries():
    scale = [GradeBand(90, "A"), GradeBand(0, "F")]

    assert score_to_letter(90, scale) == "A"
    assert score_to_letter(89.99, scale) == "F"
    assert score_to_letter(-1, scale) == "F"


@pytest.mark.parametrize(
    ("category_content", "message"),
    [
        (["not", "a", "mapping"], "must contain a mapping at the top level"),
        ({"rules": []}, "missing required 'category' string"),
        (
            {"category": "unknown", "rules": []},
            "unknown.*not present in _meta.yaml category_weights",
        ),
        (
            {"category": "naming_conventions", "rules": {"id": "NAME-T01"}},
            "'rules' must be a list",
        ),
        (
            {"category": "naming_conventions", "rules": {}},
            "'rules' must be a list",
        ),
    ],
)
def test_category_files_reject_invalid_shapes(tmp_path, category_content, message):
    pack = _write_structured_pack(tmp_path, category_content=category_content)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)


def test_duplicate_rule_ids_are_rejected_with_file_context(tmp_path):
    category_content = {
        "category": "naming_conventions",
        "rules": [_valid_rule(), _valid_rule()],
    }
    pack = _write_structured_pack(tmp_path, category_content=category_content)

    with pytest.raises(RubricValidationError, match=r"duplicate rule id 'NAME-T01'.*naming.yaml"):
        load_rubric(pack)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("not a mapping", "rule entry must be a mapping"),
        ({"name": "missing id"}, "missing 'id' string"),
        (_valid_rule(severity="urgent"), "NAME-T01: severity 'urgent'"),
        (
            _valid_rule(platforms="cja"),
            "NAME-T01: 'platforms' must be a non-empty list",
        ),
        (
            _valid_rule(platforms=None),
            "NAME-T01: 'platforms' must be a non-empty list",
        ),
        (
            _valid_rule(platforms=[]),
            "NAME-T01: 'platforms' must be a non-empty list",
        ),
        (
            _valid_rule(platforms=["CJA"]),
            "NAME-T01: unsupported platform values",
        ),
        (
            _valid_rule(platforms=["cja", "other"]),
            "NAME-T01: unsupported platform values",
        ),
        (
            _valid_rule(platforms=["cja", 1]),
            "NAME-T01: unsupported platform values",
        ),
        (_valid_rule(check=None), "NAME-T01: missing 'check' string"),
        (_valid_rule(check="not_registered"), "check function 'not_registered'.*Known checks"),
        (_valid_rule(params="not a mapping"), "NAME-T01: 'params' must be a mapping"),
        (_valid_rule(params=None), "NAME-T01: 'params' must be a mapping"),
        (_valid_rule(params={"pattern": 42}), "NAME-T01: 'pattern' must be a string"),
        (
            _valid_rule(params={"targets": "metrics"}),
            "NAME-T01: 'targets' must be a non-empty list of strings",
        ),
    ],
)
def test_rule_entries_reject_invalid_fields_with_rule_context(tmp_path, entry, message):
    category_content = {"category": "naming_conventions", "rules": [entry]}
    pack = _write_structured_pack(tmp_path, category_content=category_content)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)


def test_rubric_audit_inventory_matches_both_shipped_pack_definitions():
    audit = (REPO_ROOT / "docs" / "RUBRIC_AUDIT.md").read_text(encoding="utf-8")
    headings = {
        "schema_hygiene": "Schema hygiene",
        "naming_consistency": "Naming consistency",
        "segment_complexity": "Segment complexity",
        "calc_metric_maint": "Calculated metrics",
        "attribution_coverage": "Attribution",
        "governance_posture": "Governance",
    }

    inventories: list[dict[str, set[str]]] = []
    for pack_name in ("strict", "pragmatic"):
        rubric = load_rubric(REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / pack_name)
        assert rubric.version == "3.0"
        by_category: dict[str, set[str]] = {}
        for rule in rubric.rules:
            by_category.setdefault(rule.category, set()).add(rule.id)
        inventories.append(by_category)

    assert inventories[0] == inventories[1]
    for category, heading in headings.items():
        expected_ids = inventories[0][category]
        match = re.search(
            rf"^## {re.escape(heading)} \((\d+) bundled rules\)\n(.*?)(?=^## |\Z)",
            audit,
            re.MULTILINE | re.DOTALL,
        )
        assert match, f"missing audit section for {category}"
        assert int(match.group(1)) == len(expected_ids)
        table_ids = set(re.findall(r"^\|\s*([A-Z]+-\d+)\s*\|", match.group(2), re.MULTILINE))
        assert table_ids == expected_ids


@pytest.mark.parametrize("check", ["broken_references", "calc_formula_broken_refs"])
@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, [], {}])
def test_reference_policy_flag_requires_a_literal_boolean(tmp_path, check, value):
    flag = "exclude_unresolved_calculated_metric_segments"
    pack = _write_structured_pack(
        tmp_path,
        category_content={
            "category": "naming_conventions",
            "rules": [_valid_rule(id="CUSTOM-REFERENCE", check=check, params={flag: value})],
        },
    )
    with pytest.raises(RubricValidationError, match=f"CUSTOM-REFERENCE.*{flag}.*boolean"):
        load_rubric(pack)


@pytest.mark.parametrize("check", ["broken_references", "calc_formula_broken_refs"])
@pytest.mark.parametrize(
    "params",
    [
        {},
        {"exclude_unresolved_calculated_metric_segments": False},
        {"exclude_unresolved_calculated_metric_segments": True},
    ],
)
def test_reference_policy_flag_accepts_opt_in_opt_out_and_legacy(tmp_path, check, params):
    pack = _write_structured_pack(
        tmp_path,
        category_content={
            "category": "naming_conventions",
            "rules": [_valid_rule(id="CUSTOM-REFERENCE", check=check, params=params)],
        },
    )
    assert load_rubric(pack).rules[0].params == params


@pytest.mark.parametrize("severity", [[], {}, None, True, 7, "urgent"])
def test_rule_severity_rejects_noncanonical_values(tmp_path, severity):
    pack = _write_structured_pack(
        tmp_path,
        category_content={
            "category": "naming_conventions",
            "rules": [_valid_rule(severity=severity)],
        },
    )
    with pytest.raises(RubricValidationError, match="severity"):
        load_rubric(pack)


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_valid_yaml_neighbors_remain_accepted(tmp_path, severity):
    meta = _valid_meta()
    meta["description"] = "Unicode café 日本語"
    meta["category_weights"] = {"naming_conventions": 1, "unused": 0}
    meta["grade_scale"] = [{"min": 100, "grade": "A"}, {"min": 0, "grade": "F"}]
    pack = _write_structured_pack(
        tmp_path,
        meta=meta,
        category_content={
            "category": "naming_conventions",
            "rules": [_valid_rule(severity=severity)],
        },
    )
    for name in ("_meta.yaml", "naming.yaml"):
        with (pack / name).open("a", encoding="utf-8") as handle:
            handle.write("x_unused_scalar: 2026-10-16\nx_unused_integer: !!int 12\n")
    rubric = load_rubric(pack)
    assert rubric.rules[0].severity == severity
    assert rubric.description == meta["description"]
    assert rubric.category_weights == meta["category_weights"]
    assert [band.min_score for band in rubric.grade_scale] == [100, 0]


def test_yaml_alias_rejected_with_named_file(tmp_path):
    from sdr_grader.rules.suppression import load_suppression

    _write_structured_pack(tmp_path)
    (tmp_path / "_meta.yaml").write_text("a: &x foo\nb: *x\n", encoding="utf-8")
    with pytest.raises(RubricValidationError, match=r"_meta\.yaml.*aliases are not supported"):
        load_rubric(tmp_path)
    cfg = tmp_path / ".sdr-grader.yaml"
    cfg.write_text("a: &x foo\nb: *x\n", encoding="utf-8")
    with pytest.raises(
        RubricValidationError, match=r"\.sdr-grader\.yaml.*aliases are not supported"
    ):
        load_suppression(cfg)


def test_yaml_alias_bomb_fails_fast(tmp_path, capsys):
    from sdr_grader.cli.exit_codes import RUBRIC_VALIDATION_FAILURE
    from sdr_grader.cli.main import main

    lines = ["a0: &a0 [x,x,x,x,x,x,x,x,x]"]
    for i in range(1, 7):
        lines.append(f"a{i}: &a{i} [" + ",".join([f"*a{i - 1}"] * 9) + "]")
    lines.append("suppress: [{rule: CALC-001, reason: *a6}]")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "out.html"
    rc = main(
        [
            str(REPO_ROOT / "tests/fixtures/cja_snapshot_clean.json"),
            "--output",
            str(out),
            "--suppress-config",
            str(cfg),
        ]
    )
    err = capsys.readouterr().err
    assert rc == RUBRIC_VALIDATION_FAILURE
    assert len(err) < 1000
    assert not out.exists()


def test_yaml_deep_nesting_is_validation_error(tmp_path, capsys):
    from sdr_grader.cli.exit_codes import RUBRIC_VALIDATION_FAILURE
    from sdr_grader.cli.main import main

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("suppress: " + "[" * 5000 + "]" * 5000, encoding="utf-8")
    rc = main(
        [
            str(REPO_ROOT / "tests/fixtures/cja_snapshot_clean.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--suppress-config",
            str(cfg),
        ]
    )
    err = capsys.readouterr().err
    assert rc == RUBRIC_VALIDATION_FAILURE
    assert "Traceback" not in err


@pytest.mark.parametrize(
    "where,field,value",
    [
        ("rule", "name", {"a": 1}),
        ("rule", "rationale", ["x"]),
        ("rule", "remediation", ["x"]),
        ("meta", "version", [1, 2]),
        ("supp", "reason", [1, 2]),
    ],
)
def test_text_fields_require_strings(tmp_path, where, field, value):
    from sdr_grader.rules.suppression import load_suppression

    if where == "rule":
        _write_structured_pack(
            tmp_path,
            category_content={
                "category": "naming_conventions",
                "rules": [_valid_rule(**{field: value})],
            },
        )
        with pytest.raises(RubricValidationError):
            load_rubric(tmp_path)
    elif where == "meta":
        meta = _valid_meta()
        meta[field] = value
        _write_structured_pack(tmp_path, meta=meta)
        with pytest.raises(RubricValidationError):
            load_rubric(tmp_path)
    else:
        cfg = tmp_path / ".sdr-grader.yaml"
        cfg.write_text(
            yaml.safe_dump({"suppress": [{"rule": "X-1", field: value}]}), encoding="utf-8"
        )
        with pytest.raises(RubricValidationError):
            load_suppression(cfg)


def test_version_accepts_numeric_scalar(tmp_path):
    meta = _valid_meta()
    meta["version"] = 3.0
    _write_structured_pack(tmp_path, meta=meta)
    assert load_rubric(tmp_path).version == "3.0"


def test_validation_messages_do_not_repr_collections(tmp_path):
    from sdr_grader.rules.suppression import load_suppression

    cfg = tmp_path / ".sdr-grader.yaml"
    cfg.write_text("severity_overrides: {CALC-001: [a, b, c]}\n", encoding="utf-8")
    with pytest.raises(RubricValidationError) as exc:
        load_suppression(cfg)
    assert "list" in str(exc.value)
    assert "['a'" not in str(exc.value)


def test_describe_value_truncates_long_strings_and_names_containers():
    from sdr_grader.rules.yaml_io import describe_value

    result = describe_value("x" * 200)
    assert len(result) == 80
    assert result.endswith("...")
    assert describe_value([1, 2]) == "list"


def test_boolean_meta_version_is_rejected(tmp_path):
    meta = _valid_meta()
    meta["version"] = True
    _write_structured_pack(tmp_path, meta=meta)
    with pytest.raises(RubricValidationError):
        load_rubric(tmp_path)


@pytest.mark.parametrize("bad_id", ["\x1b[2J", "X" * 65, "A" * 10_000])
def test_rule_id_must_be_bounded_printable_text(tmp_path, bad_id):
    pack = _write_structured_pack(
        tmp_path,
        category_content={"category": "naming_conventions", "rules": [_valid_rule(id=bad_id)]},
    )
    with pytest.raises(RubricValidationError) as exc:
        load_rubric(pack)
    message = str(exc.value)
    assert "rule id must be printable text of at most 64 characters" in message
    assert "\x1b" not in message
    assert len(message) < 200


def test_colliding_long_category_weight_keys_are_bounded(tmp_path):
    key = "A" * 10_000
    meta = _valid_meta()
    meta["category_weights"] = {key: 0.5, key.lower(): 0.5}
    _write_structured_pack(tmp_path, meta=meta)
    with pytest.raises(RubricValidationError) as exc:
        load_rubric(tmp_path)
    assert len(str(exc.value)) < 300


def test_duplicate_rule_id_message_is_bounded(tmp_path):
    category_content = {
        "category": "naming_conventions",
        "rules": [_valid_rule(id="X" * 64), _valid_rule(id="X" * 64)],
    }
    pack = _write_structured_pack(tmp_path, category_content=category_content)
    with pytest.raises(RubricValidationError) as exc:
        load_rubric(pack)
    assert len(str(exc.value)) < 300


def test_invalid_regex_message_is_bounded(tmp_path):
    pattern = "(\x1b" + "a" * 10_000
    pack = _write_structured_pack(
        tmp_path,
        category_content={
            "category": "naming_conventions",
            "rules": [_valid_rule(params={"pattern": pattern})],
        },
    )
    with pytest.raises(RubricValidationError) as exc:
        load_rubric(pack)
    assert len(str(exc.value)) < 300
    assert "\x1b" not in str(exc.value)


def test_grade_scale_descending_message_is_bounded(tmp_path):
    label = "\x1b" + "G" * 10_000
    meta = _valid_meta()
    meta["grade_scale"] = [{"min": 90, "grade": label}, {"min": 90, "grade": label}]
    _write_structured_pack(tmp_path, meta=meta)
    with pytest.raises(RubricValidationError) as exc:
        load_rubric(tmp_path)
    assert len(str(exc.value)) < 300
    assert "\x1b" not in str(exc.value)


def test_param_not_declared_by_its_check_is_rejected(tmp_path):
    with pytest.raises(RubricValidationError) as exc:
        _load_with_params(tmp_path, {"threshold": 0.2}, check="regex_match_id")
    message = str(exc.value)
    assert "NAME-T01 params: unknown key 'threshold'" in message
    assert "'pattern'" in message and "'targets'" in message


def test_misspelled_param_gets_hint(tmp_path):
    with pytest.raises(RubricValidationError, match="did you mean 'threshold'"):
        _load_with_params(tmp_path, {"treshold": 0.2}, check="missing_descriptions")


def test_singular_target_typo_fails_at_load(tmp_path):
    with pytest.raises(RubricValidationError, match="'target'.*did you mean 'dimensions'"):
        _load_with_params(tmp_path, {"target": "dimensons"}, check="prefix_consistency")


@pytest.mark.parametrize(
    ("check", "params", "fragment"),
    [
        ("calc_deprecated_allocations", {"deprecated_allocations": "linear"}, "list of strings"),
        ("semantic_consistency", {"synonym_groups": [["visit"]]}, "at least 2"),
        ("snapshot_age", {"reference_date": "someday"}, "date or timestamp"),
        ("doc_drift", {"last_sdr_update_at": "soon"}, "date or timestamp"),
        ("prefix_consistency", {"tag_filter": 3}, "must be a string"),
        ("launch_required_data_elements", {"required": "page_name"}, "list of strings"),
        ("sdr_doc_absent", {"sdr_doc_present": "maybe"}, "expected boolean"),
        ("sdr_doc_absent", {"sdr_doc_present": True, "SDR Doc Present": "false"}, "conflicting"),
        ("regex_match_id", {"targets": []}, "non-empty list"),
    ],
)
def test_specialized_params_validated_at_load(tmp_path, check, params, fragment):
    with pytest.raises(RubricValidationError, match=fragment):
        _load_with_params(tmp_path, params, check=check)


def test_null_pattern_and_targets_fail_at_load(tmp_path):
    with pytest.raises(RubricValidationError, match="'pattern' must be a string"):
        _load_with_params(tmp_path, {"pattern": None}, check="regex_match_id")
    with pytest.raises(RubricValidationError, match="'targets' must be a non-empty list"):
        _load_with_params(tmp_path, {"targets": None}, check="regex_match_id")


def test_unquoted_yaml_dates_load_for_timestamp_params(tmp_path):
    (tmp_path / "_meta.yaml").write_text(
        yaml.safe_dump(_valid_meta(), sort_keys=False), encoding="utf-8"
    )
    (tmp_path / "naming.yaml").write_text(
        "category: naming_conventions\n"
        "rules:\n"
        "  - id: GOV-T01\n"
        "    name: t\n"
        "    severity: low\n"
        "    platforms: [cja]\n"
        "    check: snapshot_age\n"
        "    params:\n"
        "      reference_date: 2026-01-01\n",
        encoding="utf-8",
    )
    rubric = load_rubric(tmp_path)
    assert str(rubric.rules[0].params["reference_date"]) == "2026-01-01"


def test_nullable_params_accept_null(tmp_path):
    _load_with_params(tmp_path, {"synonym_groups": None}, check="semantic_consistency")
    _load_with_params(tmp_path, {"tag_filter": None}, check="prefix_consistency")
    _load_with_params(tmp_path, {"sdr_doc_present": None}, check="sdr_doc_absent")


def test_x_param_keys_are_accepted_and_preserved(tmp_path):
    rubric = _load_with_params(
        tmp_path, {"x_owner": "team", "threshold": 0.2}, check="missing_descriptions"
    )
    assert rubric.rules[0].params == {"x_owner": "team", "threshold": 0.2}


@pytest.mark.parametrize(
    ("meta", "category_content", "fragment"),
    [
        ({**_valid_meta(), "grade_scal": []}, _DEFAULT, "_meta.yaml: unknown key 'grade_scal'"),
        (
            {
                **_valid_meta(),
                "grade_scale": [
                    {"min": 90, "grade": "A", "label": "x"},
                    {"min": 0, "grade": "F"},
                ],
            },
            _DEFAULT,
            "grade_scale entry: unknown key 'label'",
        ),
        (
            _DEFAULT,
            {"category": "naming_conventions", "rule": [], "rules": [_valid_rule()]},
            "naming.yaml: unknown key 'rule'; did you mean 'rules'?",
        ),
        (
            _DEFAULT,
            {"category": "naming_conventions", "rules": [_valid_rule(severty="low")]},
            "naming.yaml NAME-T01: unknown key 'severty'; did you mean 'severity'?",
        ),
    ],
)
def test_unknown_keys_rejected_at_each_pack_level(tmp_path, meta, category_content, fragment):
    pack = _write_structured_pack(tmp_path, meta=meta, category_content=category_content)
    with pytest.raises(RubricValidationError) as exc:
        load_rubric(pack)
    assert fragment in str(exc.value)


def test_x_keys_accepted_at_every_pack_level(tmp_path):
    meta = {**_valid_meta(), "x_owner": "team"}
    meta["grade_scale"] = [{"min": 90, "grade": "A", "x_note": "n"}, {"min": 0, "grade": "F"}]
    category_content = {
        "category": "naming_conventions",
        "x_reviewed": "2026-10-27",
        "rules": [_valid_rule(x_ticket="SDR-1", params={"x_why": "n"})],
    }
    pack = _write_structured_pack(tmp_path, meta=meta, category_content=category_content)
    rubric = load_rubric(pack)
    assert [r.id for r in rubric.rules] == ["NAME-T01"]


def test_x_key_in_category_weights_is_read_as_a_category_name(tmp_path):
    # Data-keyed maps are not skipped: an x_ key there is an ordinary name.
    meta = {**_valid_meta(), "category_weights": {"naming_conventions": 1.0, "x_other": 0.0}}
    rubric = load_rubric(_write_structured_pack(tmp_path, meta=meta))
    assert "x_other" in rubric.category_weights


def test_non_string_rule_entry_key_is_config_error(tmp_path):
    (tmp_path / "_meta.yaml").write_text(
        yaml.safe_dump(_valid_meta(), sort_keys=False), encoding="utf-8"
    )
    (tmp_path / "naming.yaml").write_text(
        "category: naming_conventions\n"
        "rules:\n"
        "  - id: NAME-T01\n"
        "    severity: low\n"
        "    platforms: [cja]\n"
        "    check: regex_match_id\n"
        "    yes: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(RubricValidationError, match="NAME-T01: unknown key True"):
        load_rubric(tmp_path)


def test_bundled_packs_load_under_strict_keys():
    for pack in ("strict", "pragmatic", "aa-admin"):
        rubric = load_rubric(REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / pack)
        assert rubric.rules

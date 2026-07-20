"""Load-time validation of cross-check rule params (spec F8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.rules.rubric import GradeBand, load_rubric, score_to_letter

_DEFAULT = object()


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
        (_valid_rule(platforms="cja"), "NAME-T01: 'platforms' must be a list"),
        (_valid_rule(check=None), "NAME-T01: missing 'check' string"),
        (_valid_rule(check="not_registered"), "check function 'not_registered'.*Known checks"),
        (_valid_rule(params="not a mapping"), "NAME-T01: 'params' must be a mapping"),
        (_valid_rule(params={"pattern": 42}), "NAME-T01: 'pattern' must be a string"),
        (
            _valid_rule(params={"targets": "metrics"}),
            "NAME-T01: 'targets' must be a list of strings",
        ),
    ],
)
def test_rule_entries_reject_invalid_fields_with_rule_context(tmp_path, entry, message):
    category_content = {"category": "naming_conventions", "rules": [entry]}
    pack = _write_structured_pack(tmp_path, category_content=category_content)

    with pytest.raises(RubricValidationError, match=message):
        load_rubric(pack)

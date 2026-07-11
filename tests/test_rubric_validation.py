"""Load-time validation of cross-check rule params (spec F8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.rules.rubric import load_rubric

META = """\
pack: test
version: "1"
description: test pack
category_weights:
  naming_conventions: 1.0
severity_weights:
  critical: 10
  high: 5
  medium: 3
  low: 1
grade_scale:
  - {min: 90, grade: A}
  - {min: 0, grade: F}
"""

RULES = """\
category: naming_conventions
rules:
  - id: NAME-T01
    name: test rule
    severity: low
    check: regex_match_id
    params:
      {param_line}
"""


def _write_pack(tmp_path: Path, param_line: str) -> Path:
    (tmp_path / "_meta.yaml").write_text(META, encoding="utf-8")
    (tmp_path / "naming.yaml").write_text(
        RULES.format(param_line=param_line), encoding="utf-8"
    )
    return tmp_path


def test_invalid_regex_pattern_fails_at_load(tmp_path):
    pack = _write_pack(tmp_path, 'pattern: "["')
    with pytest.raises(RubricValidationError, match="pattern"):
        load_rubric(pack)


def test_unknown_target_fails_at_load(tmp_path):
    pack = _write_pack(tmp_path, "targets: [raw]")
    with pytest.raises(RubricValidationError, match="targets"):
        load_rubric(pack)


def test_valid_params_still_load(tmp_path):
    pack = _write_pack(tmp_path, 'pattern: "^[a-z]+$"')
    rubric = load_rubric(pack)
    assert [r.id for r in rubric.rules] == ["NAME-T01"]

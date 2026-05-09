"""Tests for grade computation: score -> letter and weight aggregation."""

from __future__ import annotations

import pytest

from sdr_grader.core.grade_calc import compute_grade, score_to_letter
from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.rubric import GradeBand, Rubric, RuleDefinition


@pytest.fixture
def grade_scale() -> list[GradeBand]:
    return [
        GradeBand(min_score=93, grade="A"),
        GradeBand(min_score=90, grade="A−"),
        GradeBand(min_score=87, grade="B+"),
        GradeBand(min_score=83, grade="B"),
        GradeBand(min_score=80, grade="B−"),
        GradeBand(min_score=70, grade="C"),
        GradeBand(min_score=60, grade="D"),
        GradeBand(min_score=0, grade="F"),
    ]


def _rule(rule_id: str, severity: str, category: str = "schema_hygiene") -> RuleDefinition:
    return RuleDefinition(
        id=rule_id,
        name=rule_id,
        severity=severity,
        platforms=["cja"],
        check="missing_descriptions",
        category=category,
        params={},
    )


def _finding(rule_id: str, severity: str = "medium") -> Finding:
    return Finding(
        id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        category="schema hygiene",
        title="finding",
        body=[FindingBlock(kind="paragraph", html="x")],
    )


# ---------------------------------------------------------------------------
# score_to_letter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "A"),
        (93, "A"),
        (92.999, "A−"),
        (90, "A−"),
        (88, "B+"),
        (83, "B"),
        (80, "B−"),
        (75, "C"),
        (60, "D"),
        (59.99, "F"),
        (0, "F"),
    ],
)
def test_score_to_letter_maps_descending_bands(score, expected, grade_scale):
    assert score_to_letter(score, grade_scale) == expected


def test_score_to_letter_negative_score_falls_through_to_lowest_band(grade_scale):
    assert score_to_letter(-5, grade_scale) == "F"


# ---------------------------------------------------------------------------
# compute_grade
# ---------------------------------------------------------------------------


def test_compute_grade_passes_all_rules_when_no_findings(grade_scale):
    rubric = Rubric(
        pack="t",
        version="1",
        description="",
        category_weights={"schema_hygiene": 1.0},
        severity_weights={"critical": 4, "high": 3, "medium": 2, "low": 1},
        grade_scale=grade_scale,
        rules=[_rule("R1", "high"), _rule("R2", "medium")],
    )
    result = compute_grade(rubric, [])
    assert result.overall_pct == 100
    assert result.overall_grade == "A"
    assert result.categories[0].pct == 100


def test_compute_grade_one_fired_rule_drops_category_by_severity_weight(grade_scale):
    rubric = Rubric(
        pack="t",
        version="1",
        description="",
        category_weights={"schema_hygiene": 1.0},
        severity_weights={"critical": 4, "high": 3, "medium": 2, "low": 1},
        grade_scale=grade_scale,
        rules=[_rule("R-HIGH", "high"), _rule("R-MED", "medium"), _rule("R-LOW", "low")],
    )
    # Only the medium rule fires. sev_total = 3 + 2 + 1 = 6, sev_failed = 2.
    # Category pct = round((1 - 2/6) * 100) = round(66.67) = 67.
    findings = [_finding("R-MED", severity="medium")]
    result = compute_grade(rubric, findings)
    assert result.categories[0].pct == 67
    assert result.categories[0].rules_failed == 1
    assert result.categories[0].rules_total == 3


def test_compute_grade_zero_weight_categories_excluded(grade_scale):
    rubric = Rubric(
        pack="t",
        version="1",
        description="",
        category_weights={"schema_hygiene": 1.0, "naming_consistency": 0.0},
        severity_weights={"critical": 4, "high": 3, "medium": 2, "low": 1},
        grade_scale=grade_scale,
        rules=[
            _rule("SCH-1", "medium", category="schema_hygiene"),
            _rule("NAME-1", "high", category="naming_consistency"),
        ],
    )
    # Naming rule fires, but its category weight is 0 so it doesn't count.
    findings = [_finding("NAME-1", severity="high")]
    result = compute_grade(rubric, findings)
    assert result.overall_pct == 100
    assert len(result.categories) == 1
    assert result.categories[0].slug == "schema_hygiene"


def test_compute_grade_weighted_average_across_categories(grade_scale):
    rubric = Rubric(
        pack="t",
        version="1",
        description="",
        category_weights={"schema_hygiene": 0.5, "naming_consistency": 0.5},
        severity_weights={"critical": 4, "high": 3, "medium": 2, "low": 1},
        grade_scale=grade_scale,
        rules=[
            _rule("SCH-1", "medium", category="schema_hygiene"),
            _rule("NAME-1", "medium", category="naming_consistency"),
        ],
    )
    # Naming fires (0%), schema clean (100%) -> overall = 50.
    findings = [_finding("NAME-1", severity="medium")]
    result = compute_grade(rubric, findings)
    assert result.overall_pct == 50
    assert {c.slug: c.pct for c in result.categories} == {
        "schema_hygiene": 100,
        "naming_consistency": 0,
    }


def test_compute_grade_caps_pct_in_zero_to_hundred(grade_scale):
    rubric = Rubric(
        pack="t",
        version="1",
        description="",
        category_weights={"schema_hygiene": 1.0},
        severity_weights={"critical": 4, "high": 3, "medium": 2, "low": 1},
        grade_scale=grade_scale,
        rules=[_rule("R", "critical")],
    )
    findings = [_finding("R", severity="critical")]
    result = compute_grade(rubric, findings)
    assert 0 <= result.overall_pct <= 100
    assert result.overall_pct == 0

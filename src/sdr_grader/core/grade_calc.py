"""Score and grade computation.

Algorithm (SPEC §6 makes the inputs explicit; the algorithm itself is
calibrated here):

- For each category with non-zero weight:
    rules_in_category = rubric rules where rule.category == slug
    sev_total = sum(severity_weight[r.severity] for r in rules_in_category)
    sev_failed = sum(severity_weight[r.severity] for r in rules_in_category
                     if any finding has id == r.id)
    category_pct = round((1 - sev_failed / sev_total) * 100), or 100 when
                   sev_total is 0 (no rules implemented yet for this category).

- overall_pct = weighted average of category_pct across non-zero-weight
  categories, rounded to int. Letter grade derived via the descending
  grade_scale bands.

This is intentionally simple. Calibration (caps, partial credit per finding,
non-linear penalties) is a Phase 5/6 conversation once more rules ship.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdr_grader.render import Finding
from sdr_grader.rules.rubric import GradeBand, Rubric


@dataclass(frozen=True)
class CategoryScore:
    slug: str
    weight: float
    pct: int
    grade: str
    rules_total: int
    rules_failed: int


@dataclass(frozen=True)
class GradeResult:
    overall_pct: int
    overall_grade: str
    categories: list[CategoryScore]


def compute_grade(rubric: Rubric, findings: list[Finding]) -> GradeResult:
    """Compute the full grade result from a rubric and the engine's findings."""
    fired_rule_ids = {f.id for f in findings}
    categories: list[CategoryScore] = []
    weighted_sum = 0.0
    weight_total = 0.0

    for slug, weight in rubric.category_weights.items():
        if weight <= 0:
            continue
        rules_in_cat = [r for r in rubric.rules if r.category == slug]
        sev_total = sum(rubric.severity_weights[r.severity] for r in rules_in_cat)
        sev_failed = sum(
            rubric.severity_weights[r.severity]
            for r in rules_in_cat
            if r.id in fired_rule_ids
        )
        rules_failed = sum(1 for r in rules_in_cat if r.id in fired_rule_ids)

        pct = 100 if sev_total == 0 else round((1 - sev_failed / sev_total) * 100)
        pct = max(0, min(100, pct))
        grade = score_to_letter(pct, rubric.grade_scale)

        categories.append(
            CategoryScore(
                slug=slug,
                weight=weight,
                pct=pct,
                grade=grade,
                rules_total=len(rules_in_cat),
                rules_failed=rules_failed,
            )
        )
        weighted_sum += pct * weight
        weight_total += weight

    overall_pct = 100 if weight_total == 0 else round(weighted_sum / weight_total)
    overall_pct = max(0, min(100, overall_pct))
    overall_grade = score_to_letter(overall_pct, rubric.grade_scale)

    return GradeResult(
        overall_pct=overall_pct,
        overall_grade=overall_grade,
        categories=categories,
    )


def score_to_letter(score: float, scale: list[GradeBand]) -> str:
    """Map a numeric score to its letter grade.

    Bands are validated to be strictly descending at rubric load time.
    """
    for band in scale:
        if score >= band.min_score:
            return band.grade
    return scale[-1].grade

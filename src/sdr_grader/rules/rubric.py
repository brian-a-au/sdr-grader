"""Rubric loader and validation.

A "rubric pack" is a directory containing:
- _meta.yaml: pack metadata (weights, severity, grade scale, version)
- <category>.yaml: one file per category, each with a list of rule definitions

Loading validates: every rule has a registered check function, severities are
known, category weights sum to 1.0 (within tolerance), rule IDs are unique,
and grade scale is monotonic. Failures raise RubricValidationError loudly.

See SPEC §6 for the YAML shapes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.rules.registry import _import_all_checks, get_check, registered_names

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
WEIGHT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class GradeBand:
    min_score: float
    grade: str


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    severity: str
    platforms: list[str]
    check: str
    category: str
    params: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    remediation: str = ""


@dataclass(frozen=True)
class Rubric:
    pack: str
    version: str
    description: str
    category_weights: dict[str, float]
    severity_weights: dict[str, int]
    grade_scale: list[GradeBand]
    rules: list[RuleDefinition]

    @property
    def categories_in_use(self) -> list[str]:
        """Categories with non-zero weight, ordered as in _meta.yaml."""
        return [name for name, w in self.category_weights.items() if w > 0]


def load_rubric(pack_dir: str | Path) -> Rubric:
    """Load and validate a rubric pack from disk."""
    _import_all_checks()
    pack_path = Path(pack_dir)
    if not pack_path.is_dir():
        raise RubricValidationError(f"rubric pack directory not found: {pack_path}")

    meta = _load_meta(pack_path)
    pack_name = _require_string(meta, "pack")
    version = _require_string(meta, "version", coerce=True)
    description = str(meta.get("description", "")).strip()

    category_weights = _validate_category_weights(meta.get("category_weights"))
    severity_weights = _validate_severity_weights(meta.get("severity_weights"))
    grade_scale = _validate_grade_scale(meta.get("grade_scale"))

    rules = _load_rules(pack_path, allowed_categories=set(category_weights))

    return Rubric(
        pack=pack_name,
        version=version,
        description=description,
        category_weights=category_weights,
        severity_weights=severity_weights,
        grade_scale=grade_scale,
        rules=rules,
    )


# ---------------------------------------------------------------------------
# Meta loading
# ---------------------------------------------------------------------------


def _load_meta(pack_path: Path) -> dict[str, Any]:
    meta_path = pack_path / "_meta.yaml"
    if not meta_path.exists():
        raise RubricValidationError(f"missing required _meta.yaml in {pack_path}")
    with meta_path.open(encoding="utf-8") as fh:
        meta = yaml.safe_load(fh) or {}
    if not isinstance(meta, dict):
        raise RubricValidationError(f"_meta.yaml must be a mapping, got {type(meta).__name__}")
    return meta


def _validate_category_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise RubricValidationError("_meta.yaml is missing 'category_weights' mapping")
    weights: dict[str, float] = {}
    for k, v in value.items():
        try:
            weights[str(k)] = float(v)
        except (TypeError, ValueError) as exc:
            raise RubricValidationError(
                f"category_weights[{k!r}] is not numeric ({v!r})"
            ) from exc
    seen_slugs: dict[str, str] = {}
    for key in weights:
        slug = key.lower().replace(" ", "_")
        if slug in seen_slugs:
            raise RubricValidationError(
                f"category_weights keys {seen_slugs[slug]!r} and {key!r} collapse to "
                f"the same category slug {slug!r}"
            )
        seen_slugs[slug] = key
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise RubricValidationError(
            f"category_weights must sum to 1.0; got {total:.6f}: {weights!r}"
        )
    return weights


def _validate_severity_weights(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise RubricValidationError("_meta.yaml is missing 'severity_weights' mapping")
    weights: dict[str, int] = {}
    for k, v in value.items():
        if k not in VALID_SEVERITIES:
            raise RubricValidationError(
                f"severity_weights[{k!r}] is not a valid severity "
                f"(expected one of {sorted(VALID_SEVERITIES)!r})"
            )
        try:
            weights[str(k)] = int(v)
        except (TypeError, ValueError) as exc:
            raise RubricValidationError(
                f"severity_weights[{k!r}] must be an integer (got {v!r})"
            ) from exc
    missing = VALID_SEVERITIES - weights.keys()
    if missing:
        raise RubricValidationError(
            f"severity_weights missing required keys: {sorted(missing)!r}"
        )
    return weights


def _validate_grade_scale(value: Any) -> list[GradeBand]:
    if not isinstance(value, list) or not value:
        raise RubricValidationError("_meta.yaml is missing 'grade_scale' list")
    bands: list[GradeBand] = []
    for entry in value:
        if not isinstance(entry, dict) or "min" not in entry or "grade" not in entry:
            raise RubricValidationError(
                f"grade_scale entry must be a mapping with 'min' and 'grade': {entry!r}"
            )
        try:
            min_score = float(entry["min"])
        except (TypeError, ValueError) as exc:
            raise RubricValidationError(
                f"grade_scale entry has non-numeric 'min': {entry!r}"
            ) from exc
        bands.append(GradeBand(min_score=min_score, grade=str(entry["grade"])))
    # Bands must be in descending order so score_to_letter can scan top-down.
    for prev, curr in zip(bands[:-1], bands[1:], strict=True):
        if curr.min_score >= prev.min_score:
            raise RubricValidationError(
                f"grade_scale must be strictly descending; got {prev.grade} ({prev.min_score}) "
                f"-> {curr.grade} ({curr.min_score})"
            )
    if bands[-1].min_score > 0:
        lowest = bands[-1].min_score
        raise RubricValidationError(
            f"grade_scale must include a band starting at 0; lowest band starts at {lowest}"
        )
    return bands


# ---------------------------------------------------------------------------
# Rule files
# ---------------------------------------------------------------------------


def _load_rules(pack_path: Path, allowed_categories: set[str]) -> list[RuleDefinition]:
    rules: list[RuleDefinition] = []
    seen_ids: set[str] = set()
    for category_file in sorted(pack_path.glob("*.yaml")):
        if category_file.name.startswith("_"):
            continue
        with category_file.open(encoding="utf-8") as fh:
            content = yaml.safe_load(fh) or {}
        if not isinstance(content, dict):
            raise RubricValidationError(
                f"{category_file.name} must contain a mapping at the top level"
            )
        category = content.get("category")
        if not isinstance(category, str) or not category:
            raise RubricValidationError(
                f"{category_file.name} is missing required 'category' string"
            )
        if category not in allowed_categories:
            raise RubricValidationError(
                f"{category_file.name} declares category {category!r} "
                f"not present in _meta.yaml category_weights"
            )
        rule_entries = content.get("rules") or []
        if not isinstance(rule_entries, list):
            raise RubricValidationError(
                f"{category_file.name} 'rules' must be a list"
            )
        for entry in rule_entries:
            rule = _validate_rule_entry(entry, category=category, source=category_file.name)
            if rule.id in seen_ids:
                raise RubricValidationError(
                    f"duplicate rule id {rule.id!r} in pack (in {category_file.name})"
                )
            seen_ids.add(rule.id)
            rules.append(rule)
    return rules


def _validate_rule_entry(entry: Any, *, category: str, source: str) -> RuleDefinition:
    if not isinstance(entry, dict):
        raise RubricValidationError(
            f"{source}: rule entry must be a mapping, got {type(entry).__name__}"
        )
    rule_id = entry.get("id")
    if not isinstance(rule_id, str) or not rule_id:
        raise RubricValidationError(f"{source}: rule entry is missing 'id' string")
    name = str(entry.get("name") or rule_id).strip()
    severity = entry.get("severity")
    if severity not in VALID_SEVERITIES:
        raise RubricValidationError(
            f"{source} {rule_id}: severity {severity!r} not one of {sorted(VALID_SEVERITIES)!r}"
        )
    platforms_raw = entry.get("platforms") or []
    if not isinstance(platforms_raw, list):
        raise RubricValidationError(f"{source} {rule_id}: 'platforms' must be a list")
    platforms = [str(p) for p in platforms_raw]
    check_name = entry.get("check")
    if not isinstance(check_name, str) or not check_name:
        raise RubricValidationError(f"{source} {rule_id}: missing 'check' string")
    try:
        get_check(check_name)
    except KeyError as exc:
        raise RubricValidationError(
            f"{source} {rule_id}: check function {check_name!r} is not registered. "
            f"Known checks: {registered_names()!r}"
        ) from exc
    params = entry.get("params") or {}
    if not isinstance(params, dict):
        raise RubricValidationError(f"{source} {rule_id}: 'params' must be a mapping")
    _validate_common_params(params, rule_id=rule_id, source=source)
    return RuleDefinition(
        id=rule_id,
        name=name,
        severity=str(severity),
        platforms=platforms,
        check=check_name,
        category=category,
        params=params,
        rationale=str(entry.get("rationale", "")).strip(),
        remediation=str(entry.get("remediation", "")).strip(),
    )


_KNOWN_TARGETS = {"metrics", "dimensions", "derived_fields", "calculated_metrics", "segments"}


def _validate_common_params(params: dict[str, Any], *, rule_id: str, source: str) -> None:
    """Validate the cross-check param conventions at load time.

    'pattern' params must compile as a regex and 'targets' params must
    name Implementation collections — a YAML typo should fail as a
    rubric error, not crash halfway through a grading run.
    """
    pattern = params.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise RubricValidationError(f"{source} {rule_id}: 'pattern' must be a string")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise RubricValidationError(
                f"{source} {rule_id}: 'pattern' is not a valid regex: {exc}"
            ) from exc
    targets = params.get("targets")
    if targets is not None:
        if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
            raise RubricValidationError(
                f"{source} {rule_id}: 'targets' must be a list of strings"
            )
        unknown = sorted(set(targets) - _KNOWN_TARGETS)
        if unknown:
            raise RubricValidationError(
                f"{source} {rule_id}: unknown 'targets' {unknown!r}; "
                f"expected names from {sorted(_KNOWN_TARGETS)!r}"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_string(meta: dict[str, Any], key: str, *, coerce: bool = False) -> str:
    value = meta.get(key)
    if value is None or value == "":
        raise RubricValidationError(f"_meta.yaml is missing required string '{key}'")
    if coerce:
        return str(value)
    if not isinstance(value, str):
        raise RubricValidationError(
            f"_meta.yaml '{key}' must be a string, got {type(value).__name__}"
        )
    return value


def score_to_letter(score: float, scale: list[GradeBand]) -> str:
    """Map a numeric score to its letter grade. Bands are descending."""
    for band in scale:
        if score >= band.min_score:
            return band.grade
    return scale[-1].grade

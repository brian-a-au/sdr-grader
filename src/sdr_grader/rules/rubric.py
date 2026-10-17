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

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.core.reference_policy import POLICY_PARAM, REFERENCE_CHECKS
from sdr_grader.rules.registry import _import_all_checks, get_check, registered_names
from sdr_grader.rules.yaml_io import describe_value, load_config_yaml

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_PLATFORMS = {"aa", "cja"}
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
    meta = load_config_yaml(meta_path)
    if not isinstance(meta, dict):
        raise RubricValidationError(f"_meta.yaml must be a mapping, got {type(meta).__name__}")
    return meta


def _validate_category_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise RubricValidationError("_meta.yaml is missing 'category_weights' mapping")
    weights: dict[str, float] = {}
    for k, v in value.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise RubricValidationError(
                f"category_weights[{describe_value(k)}] is not numeric ({describe_value(v)})"
            )
        try:
            number = float(v)
        except OverflowError as exc:
            raise RubricValidationError(
                f"category_weights[{describe_value(k)}] must be a finite number between 0 and 1"
            ) from exc
        if not math.isfinite(number) or not 0 <= number <= 1:
            raise RubricValidationError(
                f"category_weights[{describe_value(k)}] must be a finite "
                f"number between 0 and 1 (got {describe_value(v)})"
            )
        weights[str(k)] = number
    seen_slugs: dict[str, str] = {}
    for key in weights:
        slug = key.lower().replace(" ", "_")
        if slug in seen_slugs:
            raise RubricValidationError(
                f"category_weights keys {describe_value(seen_slugs[slug])} and "
                f"{describe_value(key)} collapse to "
                f"the same category slug {slug!r}"
            )
        seen_slugs[slug] = key
    total = math.fsum(weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise RubricValidationError(
            f"category_weights must sum to 1.0; got {total:.6f}: {describe_value(weights)}"
        )
    return weights


def _validate_severity_weights(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise RubricValidationError("_meta.yaml is missing 'severity_weights' mapping")
    weights: dict[str, int] = {}
    for k, v in value.items():
        if k not in VALID_SEVERITIES:
            raise RubricValidationError(
                f"severity_weights[{describe_value(k)}] is not a valid severity "
                f"(expected one of {sorted(VALID_SEVERITIES)!r})"
            )
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise RubricValidationError(
                f"severity_weights[{describe_value(k)}] must be an integer and a "
                f"positive integer (got {describe_value(v)})"
            )
        weights[str(k)] = v
    missing = VALID_SEVERITIES - weights.keys()
    if missing:
        raise RubricValidationError(f"severity_weights missing required keys: {sorted(missing)!r}")
    return weights


def _validate_grade_scale(value: Any) -> list[GradeBand]:
    if not isinstance(value, list) or not value:
        raise RubricValidationError("_meta.yaml is missing 'grade_scale' list")
    bands: list[GradeBand] = []
    for entry in value:
        if not isinstance(entry, dict) or "min" not in entry or "grade" not in entry:
            raise RubricValidationError(
                f"grade_scale entry must be a mapping with 'min' and 'grade':"
                f" {describe_value(entry)}"
            )
        raw_min = entry["min"]
        if isinstance(raw_min, bool) or not isinstance(
            raw_min,
            (int, float),
        ):
            raise RubricValidationError(
                f"grade_scale entry has non-numeric 'min': {describe_value(entry)}"
            )
        try:
            min_score = float(raw_min)
        except OverflowError as exc:
            raise RubricValidationError(
                "grade_scale entry 'min' must be a finite number between 0 and 100"
            ) from exc
        if not math.isfinite(min_score) or not 0 <= min_score <= 100:
            raise RubricValidationError(
                f"grade_scale entry 'min' must be a finite number between 0 and 100:"
                f" {describe_value(entry)}"
            )
        grade = entry["grade"]
        if not isinstance(grade, str) or not grade.strip():
            raise RubricValidationError(
                f"grade_scale entry 'grade' must be a non-empty string: {describe_value(entry)}"
            )
        bands.append(GradeBand(min_score=min_score, grade=grade.strip()))
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
        content = load_config_yaml(category_file)
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
                f"{category_file.name} declares category {describe_value(category)} "
                f"not present in _meta.yaml category_weights"
            )
        rule_entries = content.get("rules", [])
        if not isinstance(rule_entries, list):
            raise RubricValidationError(f"{category_file.name} 'rules' must be a list")
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
    name = (_text_field(entry, "name", source, rule_id) or rule_id).strip()
    severity = entry.get("severity")
    if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
        raise RubricValidationError(
            f"{source} {rule_id}: severity {describe_value(severity)} not one of "
            f"{sorted(VALID_SEVERITIES)!r}"
        )
    platforms_raw = entry.get("platforms")
    if not isinstance(platforms_raw, list) or not platforms_raw:
        raise RubricValidationError(f"{source} {rule_id}: 'platforms' must be a non-empty list")
    invalid_platforms = [
        platform
        for platform in platforms_raw
        if not isinstance(platform, str) or platform not in VALID_PLATFORMS
    ]
    if invalid_platforms:
        raise RubricValidationError(
            f"{source} {rule_id}: unsupported platform values "
            f"{describe_value(invalid_platforms)}; expected values from {sorted(VALID_PLATFORMS)!r}"
        )
    platforms = list(platforms_raw)
    check_name = entry.get("check")
    if not isinstance(check_name, str) or not check_name:
        raise RubricValidationError(f"{source} {rule_id}: missing 'check' string")
    try:
        get_check(check_name)
    except KeyError as exc:
        raise RubricValidationError(
            f"{source} {rule_id}: check function {describe_value(check_name)} is not registered. "
            f"Known checks: {registered_names()!r}"
        ) from exc
    params = entry.get("params", {})
    if not isinstance(params, dict):
        raise RubricValidationError(f"{source} {rule_id}: 'params' must be a mapping")
    if (
        check_name in REFERENCE_CHECKS
        and POLICY_PARAM in params
        and not isinstance(params[POLICY_PARAM], bool)
    ):
        raise RubricValidationError(f"{source} {rule_id}: '{POLICY_PARAM}' must be a boolean")
    _validate_common_params(params, rule_id=rule_id, source=source)
    return RuleDefinition(
        id=rule_id,
        name=name,
        severity=str(severity),
        platforms=platforms,
        check=check_name,
        category=category,
        params=params,
        rationale=_text_field(entry, "rationale", source, rule_id).strip(),
        remediation=_text_field(entry, "remediation", source, rule_id).strip(),
    )


_KNOWN_TARGETS = {"metrics", "dimensions", "derived_fields", "calculated_metrics", "segments"}


_NUMERIC_PARAMS: dict[str, tuple[type, float, float | None]] = {
    "threshold": (float, 0.0, 1.0),
    "min_consistency": (float, 0.0, 1.0),
    "min_similarity": (float, 0.0, 1.0),
    "max_complexity": (float, 0.0, None),
    "max_depth": (int, 0, None),
    "cap_days": (int, 0, None),
    "max_age_days": (int, 0, None),
}


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
            raise RubricValidationError(f"{source} {rule_id}: 'targets' must be a list of strings")
        unknown = sorted(set(targets) - _KNOWN_TARGETS)
        if unknown:
            raise RubricValidationError(
                f"{source} {rule_id}: unknown 'targets' {describe_value(unknown)}; "
                f"expected names from {sorted(_KNOWN_TARGETS)!r}"
            )
    for key, (kind, lo, hi) in _NUMERIC_PARAMS.items():
        if key not in params:
            continue
        value = params[key]
        kind_text = "a finite number" if kind is float else "an integer"
        hi_text = "inf" if hi is None else f"{hi:g}"
        message = f"{source} {rule_id}: '{key}' must be {kind_text} in [{lo:g}, {hi_text}]"
        if isinstance(value, bool):
            raise RubricValidationError(message)
        if kind is int:
            if not isinstance(value, int):
                raise RubricValidationError(message)
            number: float = value
            try:
                number = float(value)
            except OverflowError as exc:
                raise RubricValidationError(message) from exc
        else:
            if not isinstance(value, (int, float)):
                raise RubricValidationError(message)
            try:
                number = float(value)
            except OverflowError as exc:
                raise RubricValidationError(message) from exc
            if not math.isfinite(number):
                raise RubricValidationError(message)
        if number < lo or (hi is not None and number > hi):
            raise RubricValidationError(message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_field(entry: dict[str, Any], field: str, source: str, rule_id: str) -> str:
    value = entry.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RubricValidationError(f"{source} {rule_id}: '{field}' must be a string")
    return value


def _require_string(meta: dict[str, Any], key: str, *, coerce: bool = False) -> str:
    value = meta.get(key)
    if value is None or value == "":
        raise RubricValidationError(f"_meta.yaml is missing required string '{key}'")
    if coerce and isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str) or coerce:
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

"""Project-level suppression config (.sdr-grader.yaml).

Per SPEC §7: a project drops a YAML file in the working directory to
suppress noisy rules, override severities, or rebalance category weights
for their context. The file is opt-in; without it, the strict rubric runs
unmodified.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.render import Finding
from sdr_grader.rules.rubric import VALID_SEVERITIES, Rubric

DEFAULT_SUPPRESSION_FILENAME = ".sdr-grader.yaml"


@dataclass(frozen=True)
class SuppressedRule:
    rule_id: str
    reason: str
    components: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkippedRulesSummary:
    """Used in the rendered report's methodology section."""

    ids: list[str]
    reason: str


@dataclass(frozen=True)
class Suppression:
    suppressed: list[SuppressedRule] = field(default_factory=list)
    severity_overrides: dict[str, str] = field(default_factory=dict)
    category_weight_overrides: dict[str, float] = field(default_factory=dict)

    @property
    def fully_suppressed_ids(self) -> set[str]:
        return {s.rule_id for s in self.suppressed if not s.components}

    @property
    def component_suppressions(self) -> dict[str, set[str]]:
        return {
            s.rule_id: set(s.components)
            for s in self.suppressed
            if s.components
        }


def load_suppression(path: str | Path) -> Suppression:
    """Load a suppression YAML file. Missing file -> empty Suppression."""
    p = Path(path)
    if not p.exists():
        return Suppression()
    with p.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise RubricValidationError(
            f"{path}: suppression config must be a mapping, got {type(raw).__name__}"
        )
    return _parse(raw, source=str(path))


def _parse(raw: dict[str, Any], *, source: str) -> Suppression:
    suppressed: list[SuppressedRule] = []
    for entry in raw.get("suppress") or []:
        if not isinstance(entry, dict):
            raise RubricValidationError(
                f"{source}: suppress entries must be mappings; got {entry!r}"
            )
        rule_id = entry.get("rule")
        if not isinstance(rule_id, str) or not rule_id:
            raise RubricValidationError(f"{source}: suppress entry missing 'rule' string")
        reason = str(entry.get("reason", "")).strip()
        components = entry.get("components") or []
        if not isinstance(components, list):
            raise RubricValidationError(
                f"{source}: suppress[{rule_id}] 'components' must be a list"
            )
        suppressed.append(
            SuppressedRule(rule_id=rule_id, reason=reason, components=[str(c) for c in components])
        )

    severity_overrides_raw = raw.get("severity_overrides") or {}
    if not isinstance(severity_overrides_raw, dict):
        raise RubricValidationError(f"{source}: severity_overrides must be a mapping")
    severity_overrides: dict[str, str] = {}
    for rule_id, sev in severity_overrides_raw.items():
        if sev not in VALID_SEVERITIES:
            raise RubricValidationError(
                f"{source}: severity_overrides[{rule_id!r}] = {sev!r} is not a valid severity"
            )
        severity_overrides[str(rule_id)] = str(sev)

    weight_overrides_raw = raw.get("category_weights") or {}
    if not isinstance(weight_overrides_raw, dict):
        raise RubricValidationError(f"{source}: category_weights override must be a mapping")
    weight_overrides: dict[str, float] = {}
    for cat, w in weight_overrides_raw.items():
        try:
            weight_overrides[str(cat)] = float(w)
        except (TypeError, ValueError) as exc:
            raise RubricValidationError(
                f"{source}: category_weights[{cat!r}] is not numeric ({w!r})"
            ) from exc

    return Suppression(
        suppressed=suppressed,
        severity_overrides=severity_overrides,
        category_weight_overrides=weight_overrides,
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def apply_to_rubric(rubric: Rubric, suppression: Suppression) -> Rubric:
    """Return a new Rubric with severity + weight overrides applied.

    Suppressed rules stay in the rubric so the engine can still know about
    them — application happens at finding-time. Category weights are
    re-normalized so they continue to sum to 1.0.
    """
    new_rules = [
        replace(r, severity=suppression.severity_overrides.get(r.id, r.severity))
        for r in rubric.rules
    ]
    new_weights = dict(rubric.category_weights)
    for cat, w in suppression.category_weight_overrides.items():
        new_weights[cat] = w
    new_weights = _renormalize(new_weights)
    return replace(rubric, rules=new_rules, category_weights=new_weights)


def apply_to_findings(
    findings: list[Finding], suppression: Suppression
) -> list[Finding]:
    """Drop findings for fully-suppressed rules; keep others.

    Component-level suppressions are honored only when the finding has a
    1:1 link to a single component, which the current finding shape does
    not expose. They are passed through unchanged for now and noted in
    the methodology summary.
    """
    fully = suppression.fully_suppressed_ids
    if not fully and not suppression.severity_overrides:
        return list(findings)
    out: list[Finding] = []
    for f in findings:
        if f.id in fully:
            continue
        new_severity = suppression.severity_overrides.get(f.id, f.severity)
        if new_severity != f.severity:
            out.append(_with_severity(f, new_severity))
        else:
            out.append(f)
    return out


def summarize_suppressed(suppression: Suppression) -> list[SkippedRulesSummary]:
    """Group suppression entries for the rendered methodology section."""
    by_reason: dict[str, list[str]] = {}
    for s in suppression.suppressed:
        if not s.rule_id:
            continue
        key = s.reason or "(no reason recorded)"
        by_reason.setdefault(key, []).append(s.rule_id)
    return [
        SkippedRulesSummary(ids=sorted(ids), reason=reason)
        for reason, ids in by_reason.items()
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _renormalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(w for w in weights.values() if w > 0)
    if total <= 0:
        return weights
    return {k: (v / total if v > 0 else 0.0) for k, v in weights.items()}


def _with_severity(f: Finding, severity: str) -> Finding:
    return Finding(
        id=f.id,
        severity=severity,  # type: ignore[arg-type]
        category=f.category,
        title=f.title,
        body=list(f.body),
        actions=list(f.actions),
    )

"""Measure ratio / structural threshold distributions from admitted SDRs.

For each thresholded rule, this script measures the underlying ratio
(or structural maximum, depending on the rule) across every snapshot in
the explicitly admitted calibration cohort and emits a per-rule
distribution. Compatibility-only entries are excluded. The output is a
Markdown report at ``docs/threshold_calibration.md`` showing:

    rule_id | p25 | p50 | p75 | p90 | p95 | n | confidence

Percentiles are descriptive evidence, not outcome validation. Thresholds
remain maintainer judgment unless an independently reviewed calibration
method establishes what healthy and unhealthy populations look like.

This script is read-only against the corpus and writes only the output
markdown. It does not modify rule packs; the human is in the loop to
decide which thresholds to adjust based on the report.

Usage:
    uv run python scripts/calibrate_thresholds.py \\
        [--corpus tests/fixtures/private/] \\
        [--manifest tests/fixtures/private/manifest.yaml] \\
        [--output docs/threshold_calibration.md]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# Project imports — the script is intended to run from the repo root via uv.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sdr_grader.adapters import aa as aa_adapter  # noqa: E402
from sdr_grader.adapters import cja as cja_adapter  # noqa: E402
from sdr_grader.core.models import Implementation  # noqa: E402
from sdr_grader.rules.checks._helpers import (  # noqa: E402
    all_components,
    collect_referenced_ids,
)
from sdr_grader.rules.checks.attribution import (  # noqa: E402
    _looks_revenue,
    _looks_silent_last_touch,
)
from sdr_grader.rules.checks.naming import (  # noqa: E402
    _classify_casing,
    _extract_prefix,
)
from sdr_grader.rules.checks.schema_hygiene import (  # noqa: E402
    missing_description_breakdown,
)
from sdr_grader.rules.rubric import load_rubric  # noqa: E402

# ---------------------------------------------------------------------------
# Per-rule measurement functions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measurement:
    rule_id: str
    description: str
    unit: str  # "ratio" or "value"
    # Returns (numerator, denominator) for ratio rules so we can flag
    # low-denominator cohorts; or (value, None) for value-bound rules.
    fn: Callable[[Implementation], tuple[float, int | None]]


def _orphan_ratio(impl: Implementation) -> tuple[float, int | None]:
    n = len(impl.segments)
    if n == 0:
        return (0.0, 0)
    referenced = collect_referenced_ids(impl)
    orphans = sum(1 for s in impl.segments if s.id not in referenced)
    return (orphans / n, n)


def _seg_missing_desc_ratio(impl: Implementation) -> tuple[float, int | None]:
    n = len(impl.segments)
    if n == 0:
        return (0.0, 0)
    missing = sum(1 for s in impl.segments if not s.description)
    return (missing / n, n)


def _seg_max_depth(impl: Implementation) -> tuple[float, int | None]:
    if not impl.segments:
        return (0.0, 0)
    return (float(max(s.nesting_depth for s in impl.segments)), len(impl.segments))


def _calc_missing_desc_ratio(impl: Implementation) -> tuple[float, int | None]:
    n = len(impl.calculated_metrics)
    if n == 0:
        return (0.0, 0)
    missing = sum(1 for cm in impl.calculated_metrics if not cm.description)
    return (missing / n, n)


def _calc_orphan_ratio(impl: Implementation) -> tuple[float, int | None]:
    n = len(impl.calculated_metrics)
    if n == 0:
        return (0.0, 0)
    referenced = collect_referenced_ids(impl)
    orphans = sum(1 for cm in impl.calculated_metrics if cm.id not in referenced)
    return (orphans / n, n)


def _calc_max_complexity(impl: Implementation) -> tuple[float, int | None]:
    if not impl.calculated_metrics:
        return (0.0, 0)
    return (max(cm.complexity_score for cm in impl.calculated_metrics),
            len(impl.calculated_metrics))


def _configured_rule_targets(rule_id: str) -> tuple[str, ...]:
    strict_pack = PROJECT_ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"
    rubric = load_rubric(strict_pack)
    rule = next((candidate for candidate in rubric.rules if candidate.id == rule_id), None)
    if rule is None:
        raise RuntimeError(f"strict rubric is missing {rule_id}")
    targets = rule.params.get("targets")
    if not isinstance(targets, list) or not targets:
        raise RuntimeError(f"strict rubric {rule_id} must configure non-empty targets")
    return tuple(str(target) for target in targets)


SCH_003_TARGETS = _configured_rule_targets("SCH-003")


def _sch_missing_desc_ratio(impl: Implementation) -> tuple[float, int | None]:
    breakdown = missing_description_breakdown(impl, SCH_003_TARGETS)
    if not breakdown:
        return (0.0, 0)
    _target, missing, total = max(
        breakdown,
        key=lambda population: population[1] / population[2],
    )
    return (missing / total, total)


def _gov_missing_owners_ratio(impl: Implementation) -> tuple[float, int | None]:
    components = all_components(impl)
    n = len(components)
    if n == 0:
        return (0.0, 0)
    missing = sum(1 for c in components if not getattr(c, "owner", None))
    return (missing / n, n)


def _gov_missing_tags_ratio(impl: Implementation) -> tuple[float, int | None]:
    components = all_components(impl)
    n = len(components)
    if n == 0:
        return (0.0, 0)
    missing = sum(1 for c in components if not getattr(c, "tags", None))
    return (missing / n, n)


def _name_prefix_consistency(impl: Implementation) -> tuple[float, int | None]:
    """NAME-001 population: dimension prefix consistency.

    Numerator: count of dimensions matching the dominant prefix.
    Denominator: count of dimensions whose ID yielded any prefix at all
    (the rule's pool — components with no prefix can't be inconsistent).
    Returns 1.0 when the pool is too small (matches the rule's <5 skip).
    The rule fires when this ratio < min_consistency, so the calibration
    should show the inflection between healthy and unhealthy tenants.
    """
    pool = list(impl.dimensions)
    if len(pool) < 5:
        return (1.0, len(pool))  # below rule's floor; reported as "clean"
    prefixes = [_extract_prefix(c.id) for c in pool]
    present = [p for p in prefixes if p]
    if not present:
        # No dimension carries a prefix at all — the rule can't discriminate.
        # Treat as 1.0 ("clean") for the same reason the rule short-circuits.
        return (1.0, len(pool))
    counts: dict[str, int] = defaultdict(int)
    for p in present:
        counts[p] += 1
    dominant = max(counts.values())
    return (dominant / len(pool), len(pool))


def _name_casing_consistency(impl: Implementation) -> tuple[float, int | None]:
    """NAME-003 population: dimension name casing consistency.

    Numerator: count of dimensions whose name matches the dominant
    casing style. Denominator: total dimensions. Returns 1.0 when the
    pool is too small (matches the rule's <5 skip).
    """
    pool = list(impl.dimensions)
    if len(pool) < 5:
        return (1.0, len(pool))
    styles = [_classify_casing(c.name) for c in pool]
    classified = [s for s in styles if s]
    if not classified:
        return (1.0, len(pool))
    counts: dict[str, int] = defaultdict(int)
    for s in classified:
        counts[s] += 1
    dominant = max(counts.values())
    return (dominant / len(pool), len(pool))


def _attr_silent_last_touch_ratio(impl: Implementation) -> tuple[float, int | None]:
    """ATTR-001 population: revenue/conversion-named calc metrics that look
    like silent last-touch defaults — attribution_model empty or 'last-touch'
    AND no 'attribution' word in the description. Denominator is the count
    of revenue/conversion-named calc metrics on the tenant. A degenerate
    distribution here (everyone at 1.00) confirms the rule fires on every
    revenue-named calc metric without distinguishing real risk from the
    common case of leaving attribution to the query layer."""
    revenue_calcs = [
        cm
        for cm in impl.calculated_metrics
        if _looks_revenue(cm)
    ]
    n = len(revenue_calcs)
    if n == 0:
        return (0.0, 0)
    silent = sum(_looks_silent_last_touch(cm) for cm in revenue_calcs)
    return (silent / n, n)


def _attr_missing_ratio(impl: Implementation) -> tuple[float, int | None]:
    """ATTR-002 population: calc metrics with no explicit attribution_model.
    Denominator is total calc metrics. This is the exact ratio the rule
    thresholds at 0.30."""
    n = len(impl.calculated_metrics)
    if n == 0:
        return (0.0, 0)
    missing = sum(1 for cm in impl.calculated_metrics if not cm.attribution_model)
    return (missing / n, n)


def _attr_inconsistency_count(impl: Implementation) -> tuple[float, int | None]:
    """ATTR-003 population: count of (same-references, ≥2 distinct attribution
    models) conflict groups. Denominator is the count of calc metrics with
    BOTH non-empty references AND an explicit attribution_model — i.e. the
    pool that could in principle conflict."""
    by_refs: dict[frozenset[str], list[str]] = defaultdict(list)
    for cm in impl.calculated_metrics:
        if not cm.references or not cm.attribution_model:
            continue
        by_refs[frozenset(cm.references)].append(cm.attribution_model)
    conflicts = sum(
        1 for models in by_refs.values() if len(models) >= 2 and len(set(models)) >= 2
    )
    eligible = sum(len(models) for models in by_refs.values())
    return (float(conflicts), eligible)


MEASUREMENTS: list[Measurement] = [
    Measurement("SEG-003", "Orphan segment ratio (unreferenced segments / total segments)",
                "ratio", _orphan_ratio),
    Measurement("SEG-005", "Segments missing descriptions / total segments",
                "ratio", _seg_missing_desc_ratio),
    Measurement("SEG-007", "Maximum segment nesting depth in tenant",
                "value", _seg_max_depth),
    Measurement("CALC-001", "Calculated metrics missing descriptions / total",
                "ratio", _calc_missing_desc_ratio),
    Measurement("CALC-003", "Maximum calculated metric complexity score in tenant",
                "value", _calc_max_complexity),
    Measurement("CALC-005", "Orphan calculated metrics / total",
                "ratio", _calc_orphan_ratio),
    Measurement(
        "SCH-003",
        "Maximum configured-target missing-description ratio "
        f"(targets: {', '.join(SCH_003_TARGETS)})",
        "ratio",
        _sch_missing_desc_ratio,
    ),
    Measurement("GOV-004", "Components missing owner attribution / total components",
                "ratio", _gov_missing_owners_ratio),
    Measurement("GOV-005", "Components missing tags / total components",
                "ratio", _gov_missing_tags_ratio),
    Measurement(
        "NAME-001",
        "Dimension prefix consistency ratio (dominant prefix count / total dimensions). "
        "Rule fires when this ratio < min_consistency (strict 0.60, pragmatic 0.50). "
        "Lower values = more inconsistent.",
        "ratio",
        _name_prefix_consistency,
    ),
    Measurement(
        "NAME-003",
        "Dimension name casing consistency ratio (dominant casing style / total dimensions). "
        "Rule fires when this ratio < min_consistency (strict 0.60, pragmatic 0.50). "
        "Lower values = more inconsistent.",
        "ratio",
        _name_casing_consistency,
    ),
    Measurement(
        "ATTR-001",
        "Revenue/conversion calc metrics that look like silent last-touch defaults "
        "(no model or last-touch + no 'attribution' in description) / "
        "revenue/conversion-named calc metrics",
        "ratio",
        _attr_silent_last_touch_ratio,
    ),
    Measurement(
        "ATTR-002",
        "Calc metrics with no explicit attribution_model / total calc metrics",
        "ratio",
        _attr_missing_ratio,
    ),
    Measurement(
        "ATTR-003",
        "Count of (same-references, ≥2 distinct attribution models) conflict groups per tenant",
        "value",
        _attr_inconsistency_count,
    ),
]


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("entries") or []
    admitted: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        anonymization = entry.get("anonymization")
        calibration = entry.get("calibration")
        if not isinstance(anonymization, dict) or not isinstance(
            calibration,
            dict,
        ):
            continue
        reviewed_by = calibration.get("reviewed_by")
        reviewed_at = calibration.get("reviewed_at")
        if (
            anonymization.get("reviewed_descriptions") is not True
            or calibration.get("admitted") is not True
            or not isinstance(reviewed_by, str)
            or not reviewed_by.strip()
            or not isinstance(reviewed_at, str)
        ):
            continue
        try:
            parsed_review_date = datetime.strptime(
                reviewed_at,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            continue
        if parsed_review_date.isoformat() != reviewed_at:
            continue
        admitted.append(entry)
    return admitted


def _adapt_snapshot(corpus_dir: Path, entry: dict[str, Any]) -> Implementation | None:
    rel = entry.get("file")
    platform = entry.get("platform")
    if not rel or platform not in ("cja", "aa"):
        return None
    path = corpus_dir / rel
    if not path.exists():
        print(f"WARN: manifest entry {entry.get('anon_id')} points to missing file {path}",
              file=sys.stderr)
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if platform == "cja":
        return cja_adapter.adapt(raw, source=str(path))
    return aa_adapter.adapt(raw, source=str(path))


# ---------------------------------------------------------------------------
# Distribution helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _confidence(n: int, min_denominator: int, distribution_spread: float) -> str:
    """Calibration confidence based on sample size, denominators, and spread.

    A wide-spread distribution with a real inflection point is the gold
    standard. A degenerate distribution (everyone at 0 or everyone at 1)
    means the rule isn't actually discriminating — it tells us the
    threshold is meaningless, not that we're confident in it. So:
    - high: enough samples + denominators + the distribution has real spread
    - medium: enough samples + denominators but spread is narrow
    - low: thin corpus, or degenerate distribution
    """
    if n < 4 or min_denominator < 5:
        return "low"
    if distribution_spread <= 0:
        # Everyone at the same value — rule isn't discriminating.
        return "low"
    if n >= 8 and min_denominator >= 10:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _render_report(distributions: dict[str, list[tuple[float, int | None]]]) -> str:
    lines = [
        "# Threshold distribution evidence",
        "",
        f"_Generated by `scripts/calibrate_thresholds.py` on "
        f"{datetime.now(UTC).strftime('%Y-%m-%d')}._",
        "",
        "This report measures the underlying ratio or structural value for",
        "each thresholded rule across entries explicitly admitted to the",
        "calibration cohort. Percentiles are descriptive evidence only; this",
        "report does not establish calibration or independently label healthy",
        "and unhealthy populations. Threshold choices remain maintainer",
        "judgment unless separate outcome validation is recorded.",
        "",
        "See `docs/CALIBRATION_CORPUS.md` for compatibility collection and",
        "the additional human-review requirements for calibration admission.",
        "Bind release evidence to a candidate SHA and corpus revision in",
        "`docs/RELEASE_CHECKLIST.md`; a generated file alone is not approval.",
        "",
    ]

    for measurement in MEASUREMENTS:
        observations = distributions.get(measurement.rule_id, [])
        # Filter out zero-denominator observations: a tenant with 0 segments
        # contributes nothing to a segment-ratio distribution (ratio is
        # undefined). Keeping them flattens the distribution to zeros.
        meaningful = [(v, d) for (v, d) in observations if d is None or d > 0]
        values = [v for (v, _d) in meaningful]
        denominators = [d for (_v, d) in meaningful if d is not None]
        skipped = len(observations) - len(meaningful)

        lines.append(f"## {measurement.rule_id}")
        lines.append("")
        lines.append(f"_{measurement.description}_")
        lines.append("")

        if not values:
            lines.append(
                f"No meaningful observations across {len(observations)} corpus "
                "entries (all snapshots had an empty denominator — the corpus "
                "doesn't carry the data this rule measures). The threshold in "
                "the rubric pack remains expert judgment."
            )
            lines.append("")
            continue

        sorted_vals = sorted(values)
        spread = sorted_vals[-1] - sorted_vals[0]
        min_denom = min(denominators) if denominators else 0
        confidence = _confidence(len(values), min_denom, spread)

        p25 = _percentile(sorted_vals, 0.25)
        p50 = _percentile(sorted_vals, 0.50)
        p75 = _percentile(sorted_vals, 0.75)
        p90 = _percentile(sorted_vals, 0.90)
        p95 = _percentile(sorted_vals, 0.95)

        fmt = "{:.2f}" if measurement.unit == "ratio" else "{:.1f}"
        lines.append("| metric | value |")
        lines.append("|--------|-------|")
        lines.append(
            f"| n (meaningful observations) | {len(values)} "
            f"(skipped {skipped} with empty denominator) |"
        )
        lines.append(f"| min denominator | {min_denom} |")
        lines.append(f"| p25 | {fmt.format(p25)} |")
        lines.append(f"| p50 (median) | {fmt.format(p50)} |")
        lines.append(f"| p75 | {fmt.format(p75)} |")
        lines.append(f"| p90 | {fmt.format(p90)} |")
        lines.append(f"| p95 | {fmt.format(p95)} |")
        lines.append(f"| stdev | {fmt.format(statistics.pstdev(values))} |")
        lines.append(f"| confidence | **{confidence}** |")
        lines.append("")

        if spread == 0 and len(values) >= 4:
            lines.append(
                f"> **Degenerate distribution.** Every observation sits at "
                f"{fmt.format(values[0])} — the rule doesn't discriminate "
                "between tenants. Either redesign what the rule measures, "
                "or the corpus doesn't carry the field this rule grades."
            )
            lines.append("")
        elif confidence == "low":
            lines.append("> **Low confidence.** Either fewer than 4 observations,")
            lines.append("> or the underlying denominator on at least one tenant is")
            lines.append("> small enough (< 5) that the ratio is unstable. The")
            lines.append("> threshold in the rubric pack is expert judgment, not")
            lines.append("> data calibration.")
            lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path,
                        default=PROJECT_ROOT / "tests" / "fixtures" / "private",
                        help="root of the private compatibility corpus")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="path to manifest.yaml (defaults to <corpus>/manifest.yaml)")
    parser.add_argument("--output", type=Path,
                        default=PROJECT_ROOT / "docs" / "threshold_calibration.md")
    args = parser.parse_args(argv)

    manifest_path = args.manifest or (args.corpus / "manifest.yaml")
    entries = _load_manifest(manifest_path)
    if not entries:
        print(f"No calibration-admitted corpus entries found at {manifest_path}.")
        print("See docs/CALIBRATION_CORPUS.md for intake instructions.")
        print("Writing a zero-admission report.")
        args.output.write_text(
            "# Threshold distribution evidence\n\n"
            "_No private entries are currently admitted to the calibration "
            "cohort. Compatibility-only snapshots are intentionally excluded. "
            "See `docs/CALIBRATION_CORPUS.md`._\n",
            encoding="utf-8",
        )
        return 0

    distributions: dict[str, list[tuple[float, int | None]]] = {
        m.rule_id: [] for m in MEASUREMENTS
    }

    for entry in entries:
        impl = _adapt_snapshot(args.corpus, entry)
        if impl is None:
            continue
        for m in MEASUREMENTS:
            distributions[m.rule_id].append(m.fn(impl))

    report = _render_report(distributions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output} from {len(entries)} corpus entr"
          f"{'y' if len(entries) == 1 else 'ies'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

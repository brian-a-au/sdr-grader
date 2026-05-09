"""Command-line entry point.

Phase 3 wires only Mode 1 (snapshot file path). Modes 2-4 (directory,
shell-out, stdin) land in Phase 8 (SPEC §7). Exit codes mirror cja_auto_sdr
per SPEC §7.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sdr_grader.cli.exit_codes import (
    GRADE_BELOW_THRESHOLD,
    RUBRIC_VALIDATION_FAILURE,
    RUNTIME_ERROR,
    SUCCESS,
)
from sdr_grader.core.exceptions import (
    InvalidSnapshotError,
    RubricValidationError,
    UnknownPlatformError,
)
from sdr_grader.core.grader import grade
from sdr_grader.render import render
from sdr_grader.rules.rubric import load_rubric

BUNDLED_PACKS_DIR = Path(__file__).resolve().parent.parent / "rules" / "packs"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        snapshot_text = Path(args.snapshot).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"error: snapshot file not found: {args.snapshot}", file=sys.stderr)
        return RUNTIME_ERROR
    except OSError as exc:
        print(f"error: could not read snapshot {args.snapshot}: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    try:
        snapshot = json.loads(snapshot_text)
    except json.JSONDecodeError as exc:
        print(f"error: snapshot is not valid JSON: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    try:
        impl = _adapt_snapshot(snapshot, source=args.snapshot, platform_override=args.platform)
    except (InvalidSnapshotError, UnknownPlatformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    rubric_dir = _resolve_rubric_dir(args)
    if rubric_dir is None:
        return RUNTIME_ERROR

    try:
        rubric = load_rubric(rubric_dir)
    except RubricValidationError as exc:
        print(f"rubric error: {exc}", file=sys.stderr)
        return RUBRIC_VALIDATION_FAILURE

    report = grade(impl, rubric)
    html = render(report)
    output_path = Path(args.output) if args.output else _default_output_path(report)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"error: could not write output {output_path}: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    if not args.quiet:
        print(
            f"Wrote {output_path}: grade {report.grade} "
            f"({report.overall_pct}%) for {impl.instance_id}",
            file=sys.stderr,
        )

    if args.fail_below:
        return _check_threshold(report, args.fail_below, rubric)
    return SUCCESS


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdr-grader",
        description=(
            "Deterministic, rule-based linter for Adobe CJA and AA implementations. "
            "Reads a cja_auto_sdr / aa_auto_sdr JSON snapshot and emits an HTML "
            "report card."
        ),
    )
    parser.add_argument(
        "snapshot",
        help="Path to a snapshot JSON file produced by cja_auto_sdr or aa_auto_sdr.",
    )
    parser.add_argument(
        "--rubric",
        help="Path to a rubric pack directory. Overrides --pack if both are set.",
    )
    parser.add_argument(
        "--pack",
        default="strict",
        help="Name of a bundled rubric pack. Default: strict.",
    )
    parser.add_argument(
        "--platform",
        choices=["cja", "aa"],
        help="Override platform auto-detection (Phase 7+).",
    )
    parser.add_argument(
        "--output",
        help="HTML output path. Default: ./grade-{generated_at}.html.",
    )
    parser.add_argument(
        "--fail-below",
        help="Exit code 2 if the overall grade falls below this letter (e.g. 'B-').",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational stderr output.",
    )
    return parser


# ---------------------------------------------------------------------------
# Adapter dispatch
# ---------------------------------------------------------------------------


def _adapt_snapshot(snapshot, *, source: str, platform_override: str | None):
    """Phase 3 only ships the CJA adapter. Auto-detection lands in Phase 7."""
    # Lazy import to keep the CLI startup fast.
    from sdr_grader.adapters.cja import adapt as adapt_cja

    if platform_override == "aa":
        raise UnknownPlatformError(
            "AA adapter is not implemented in this release (Phase 7 work item). "
            "Re-run with a CJA snapshot or omit --platform."
        )
    # Without --platform=cja, still default to CJA in Phase 3 — Mode 1 + CJA only.
    return adapt_cja(snapshot, source=source)


# ---------------------------------------------------------------------------
# Rubric resolution
# ---------------------------------------------------------------------------


def _resolve_rubric_dir(args) -> Path | None:
    if args.rubric:
        path = Path(args.rubric)
        if not path.is_dir():
            print(f"error: rubric directory not found: {path}", file=sys.stderr)
            return None
        return path
    bundled = BUNDLED_PACKS_DIR / args.pack
    if not bundled.is_dir():
        print(
            f"error: bundled pack {args.pack!r} not found at {bundled}; "
            f"pass --rubric PATH to use a custom pack.",
            file=sys.stderr,
        )
        return None
    return bundled


# ---------------------------------------------------------------------------
# Output and threshold
# ---------------------------------------------------------------------------


def _default_output_path(report) -> Path:
    stamp = report.generated_at.strftime("%Y%m%d-%H%M%S")
    return Path(f"grade-{stamp}.html")


def _check_threshold(report, threshold_grade: str, rubric) -> int:
    threshold_pct = _grade_to_min_pct(threshold_grade, rubric)
    if threshold_pct is None:
        print(
            f"error: --fail-below value {threshold_grade!r} not found in rubric grade scale.",
            file=sys.stderr,
        )
        return RUNTIME_ERROR
    if report.overall_pct < threshold_pct:
        return GRADE_BELOW_THRESHOLD
    return SUCCESS


def _grade_to_min_pct(grade_label: str, rubric) -> float | None:
    """Look up the minimum score required to earn the given letter grade."""
    normalized = grade_label.strip().replace("-", "−")
    for band in rubric.grade_scale:
        if band.grade == normalized or band.grade == grade_label:
            return band.min_score
    return None

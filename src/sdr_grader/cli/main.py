"""Command-line entry point.

All four input modes land here (SPEC §7): snapshot file, snapshot
directory, shell-out to cja_auto_sdr / aa_auto_sdr, and stdin. Exit
codes mirror cja_auto_sdr.
"""

from __future__ import annotations

import argparse
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
from sdr_grader.input.loader import STDIN_TOKEN, load_snapshot
from sdr_grader.input.shell_out import shell_aa, shell_cja
from sdr_grader.render import cap_component_items, render
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.rules.suppression import (
    DEFAULT_SUPPRESSION_FILENAME,
    load_suppression,
)

BUNDLED_PACKS_DIR = Path(__file__).resolve().parent.parent / "rules" / "packs"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    rubric_dir = _resolve_rubric_dir(args)
    if rubric_dir is None:
        return RUNTIME_ERROR
    try:
        rubric = load_rubric(rubric_dir)
    except RubricValidationError as exc:
        print(f"rubric error: {exc}", file=sys.stderr)
        return RUBRIC_VALIDATION_FAILURE

    if args.suppress_config:
        suppression_path = Path(args.suppress_config)
        if not suppression_path.exists():
            print(
                f"error: suppression config not found: {suppression_path}",
                file=sys.stderr,
            )
            return RUNTIME_ERROR
    else:
        suppression_path = Path(DEFAULT_SUPPRESSION_FILENAME)
    try:
        suppression = load_suppression(suppression_path)
    except RubricValidationError as exc:
        print(f"rubric error: {exc}", file=sys.stderr)
        return RUBRIC_VALIDATION_FAILURE

    if args.trend:
        ignored = [
            flag
            for flag, value in (
                ("--json", args.json_output),
                ("--extra-input", args.extra_input),
                ("--distribution-data", args.distribution_data),
                ("--at", args.at),
            )
            if value
        ]
        if ignored:
            print(
                f"error: {', '.join(ignored)} not supported with --trend",
                file=sys.stderr,
            )
            return RUNTIME_ERROR
        return _run_trend(args, rubric, suppression)

    try:
        snapshot, source = _load_snapshot_for_args(args)
    except InvalidSnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    try:
        impl = _adapt_snapshot(snapshot, source=source, platform_override=args.platform)
    except (InvalidSnapshotError, UnknownPlatformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    try:
        _attach_extra_inputs(impl, args.extra_input)
    except InvalidSnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    report = grade(impl, rubric, suppression=suppression)
    report = _maybe_attach_distribution(report, args)
    if report is None:
        return RUNTIME_ERROR
    # HTML gets the display-capped copy; --json below serializes the full
    # report so no component list is ever lost to the cap (issue #5).
    html = render(cap_component_items(report))
    output_path = Path(args.output) if args.output else _default_output_path(report)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"error: could not write output {output_path}: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    if args.json_output:
        import json as _json

        from sdr_grader.render.json_output import report_to_dict

        json_path = Path(args.json_output)
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                _json.dumps(report_to_dict(report), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"error: could not write JSON {json_path}: {exc}", file=sys.stderr)
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
        nargs="?",
        help=(
            "Path to a snapshot JSON file or directory; '-' for stdin. "
            "Omit when using --dataview or --rsid."
        ),
    )
    parser.add_argument(
        "--dataview",
        help="Shell out to cja_auto_sdr against the given Data View ID (Mode 3).",
    )
    parser.add_argument(
        "--rsid",
        help="Shell out to aa_auto_sdr against the given Report Suite ID (Mode 3).",
    )
    parser.add_argument(
        "--at",
        help=(
            "Used with a snapshot directory: pick the snapshot closest to "
            "(but not after) this ISO-8601 timestamp."
        ),
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        help=(
            "Used with a snapshot directory: grade every dated snapshot and "
            "render a trend report instead of grading a single snapshot."
        ),
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
        help="Override platform auto-detection.",
    )
    parser.add_argument(
        "--output",
        help=(
            "HTML output path. Default: ./grade-{report.id}.html "
            "(e.g. grade-SDR-2026-0520-DV-PROD-WEB.html)."
        ),
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        help="Also emit a machine-readable JSON representation to PATH.",
    )
    parser.add_argument(
        "--suppress-config",
        help=("Path to a project-level suppression YAML. Default: ./.sdr-grader.yaml if present."),
    )
    parser.add_argument(
        "--distribution-data",
        help=(
            "Path to a distribution data JSON (percentile reference for the "
            "report's distribution charts). Use 'bundled' for the packaged "
            "default; omit to skip the distribution section."
        ),
    )
    parser.add_argument(
        "--extra-input",
        action="append",
        default=[],
        help=(
            "Attach a supplementary JSON input under the given key. Format: "
            "KEY=PATH. Repeat to attach multiple "
            "(--extra-input launch=launch.json --extra-input workspace=ws.json). "
            "Available to rules via Implementation.supplementary_data[KEY]."
        ),
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
# Supplementary inputs
# ---------------------------------------------------------------------------


def _attach_extra_inputs(impl, raw_specs: list[str]) -> None:
    """Parse --extra-input KEY=PATH specs and merge into supplementary_data."""
    if not raw_specs:
        return
    import json as _json

    for spec in raw_specs:
        if "=" not in spec:
            raise InvalidSnapshotError(f"--extra-input expected KEY=PATH, got {spec!r}")
        key, _, path_str = spec.partition("=")
        key = key.strip()
        if not key:
            raise InvalidSnapshotError(f"--extra-input has empty KEY in {spec!r}")
        path = Path(path_str.strip())
        if not path.is_file():
            raise InvalidSnapshotError(f"--extra-input {key}: file not found at {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidSnapshotError(
                f"--extra-input {key}: could not read {path}: {exc}"
            ) from exc
        try:
            payload = _json.loads(text)
        except _json.JSONDecodeError as exc:
            raise InvalidSnapshotError(f"--extra-input {key}: not valid JSON: {exc}") from exc
        if key in impl.supplementary_data:
            raise InvalidSnapshotError(f"--extra-input {key}: duplicate key (already attached)")
        impl.supplementary_data[key] = payload


# ---------------------------------------------------------------------------
# Distribution context
# ---------------------------------------------------------------------------


def _maybe_attach_distribution(report, args):
    """If --distribution-data was supplied, attach a Distribution block."""
    if not args.distribution_data:
        return report
    from dataclasses import replace as _replace

    from sdr_grader.core.exceptions import InvalidSnapshotError as _ISE
    from sdr_grader.render.distribution import (
        BUNDLED_PATH,
        build_distribution,
        load_distribution_data,
    )

    path = None if args.distribution_data == "bundled" else args.distribution_data
    try:
        data = load_distribution_data(path or BUNDLED_PATH)
    except _ISE as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    return _replace(report, distribution=build_distribution(report, data))


# ---------------------------------------------------------------------------
# Trend mode
# ---------------------------------------------------------------------------


def _run_trend(args, rubric, suppression) -> int:
    """Drive the trend pipeline. Requires snapshot to be a directory path."""
    from sdr_grader.core.exceptions import InvalidSnapshotError as _ISE
    from sdr_grader.trend import build_trend_report, render_trend

    if not args.snapshot:
        print("error: --trend requires a snapshot directory path", file=sys.stderr)
        return RUNTIME_ERROR
    directory = Path(args.snapshot)
    if not directory.is_dir():
        print(
            f"error: --trend requires a directory; {directory} is not one",
            file=sys.stderr,
        )
        return RUNTIME_ERROR
    try:
        trend = build_trend_report(
            directory,
            rubric,
            suppression=suppression,
            platform_override=args.platform,
        )
    except _ISE as exc:
        print(f"error: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    html = render_trend(trend)
    output_path = (
        Path(args.output)
        if args.output
        else Path(f"trend-{trend.instance_id}-{trend.latest.timestamp:%Y%m%d}.html")
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"error: could not write trend output {output_path}: {exc}", file=sys.stderr)
        return RUNTIME_ERROR

    if not args.quiet:
        latest = trend.latest.report
        print(
            f"Wrote {output_path}: trend over {len(trend.points)} snapshots, "
            f"latest grade {latest.grade} ({latest.overall_pct}%) for "
            f"{trend.instance_id}",
            file=sys.stderr,
        )
    if args.fail_below:
        return _check_threshold(trend.latest.report, args.fail_below, rubric)
    return SUCCESS


# ---------------------------------------------------------------------------
# Input-mode dispatch
# ---------------------------------------------------------------------------


def _load_snapshot_for_args(args) -> tuple[dict, str]:
    """Pick the right input mode from CLI args and return (snapshot, source)."""
    explicit_modes = sum(1 for v in (args.snapshot, args.dataview, args.rsid) if v)
    if explicit_modes == 0:
        raise InvalidSnapshotError(
            "no input specified; pass a snapshot path, '-' for stdin, "
            "or --dataview / --rsid to shell out."
        )
    if explicit_modes > 1:
        raise InvalidSnapshotError(
            "multiple input modes specified; pick one of snapshot / --dataview / --rsid."
        )
    if args.dataview:
        return shell_cja(args.dataview)
    if args.rsid:
        return shell_aa(args.rsid)
    # Mode 1, 2, or 4 — handled by the loader.
    if args.snapshot != STDIN_TOKEN and not Path(args.snapshot).exists():
        # Preserve the historical "snapshot file not found" message for the
        # explicit-file failure mode.
        raise InvalidSnapshotError(f"snapshot file not found: {args.snapshot}")
    return load_snapshot(args.snapshot, at=args.at)


# ---------------------------------------------------------------------------
# Adapter dispatch
# ---------------------------------------------------------------------------


def _adapt_snapshot(snapshot, *, source: str, platform_override: str | None):
    """Detect platform (or use override) and dispatch to the right adapter."""
    # Lazy imports keep the CLI startup fast.
    from sdr_grader.adapters.aa import adapt as adapt_aa
    from sdr_grader.adapters.cja import adapt as adapt_cja
    from sdr_grader.input.detect import detect_platform

    platform = platform_override or detect_platform(snapshot)
    if platform == "cja":
        return adapt_cja(snapshot, source=source)
    if platform == "aa":
        return adapt_aa(snapshot, source=source)
    raise UnknownPlatformError(f"unknown platform {platform!r}; expected 'cja' or 'aa'")


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
    # report.id is `SDR-{YYYY-MMDD}-{INSTANCE-TOKEN}` (see core/grader.py
    # _report_id) — already sanitized for filesystem use and keyed by
    # instance, so batch runs across many instances don't collide on
    # filename. Same-instance re-runs on the same day overwrite, which
    # mirrors --trend's `trend-{instance}-{YYYYMMDD}.html` convention.
    return Path(f"grade-{report.id}.html")


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

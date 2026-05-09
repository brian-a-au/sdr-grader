"""Aggregate sdr-grader --json outputs into a distribution.json reference.

Closes the gap until a real opt-in submission service exists (SPEC §8
deferred items). Teams that grade many implementations internally can
collect the JSON outputs into a directory, run this script, and use
the resulting file as `--distribution-data PATH` for the report's
distribution context.

Usage:

    python scripts/aggregate_distributions.py grades_dir/ -o distribution.json

The directory may contain any number of grade JSONs (one per
implementation). Each is loaded; their `overall_pct` and per-category
`pct` values feed into the percentile computation. Output matches the
schema of `src/sdr_grader/data/distribution.json`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import quantiles
from typing import Any

CATEGORY_DISPLAY_TO_SLUG = {
    "schema hygiene": "schema_hygiene",
    "naming consistency": "naming_consistency",
    "segment complexity": "segment_complexity",
    "calc metric maint": "calc_metric_maint",
    "attribution coverage": "attribution_coverage",
    "governance posture": "governance_posture",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aggregate_distributions")
    parser.add_argument("directory", help="Directory of sdr-grader --json outputs.")
    parser.add_argument(
        "-o", "--output",
        default="distribution.json",
        help="Where to write the aggregated distribution.json. Default: ./distribution.json.",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Optional human description for the produced file.",
    )
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"error: not a directory: {directory}")
        return 1

    overall: list[int] = []
    per_category: dict[str, list[int]] = {}
    n = 0
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warn: skipping {path}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        if not isinstance(data.get("overall_pct"), int):
            continue
        n += 1
        overall.append(int(data["overall_pct"]))
        for cat in data.get("categories") or []:
            if not isinstance(cat, dict):
                continue
            slug = CATEGORY_DISPLAY_TO_SLUG.get(
                str(cat.get("name", "")).lower().strip(),
                str(cat.get("name", "")).lower().replace(" ", "_"),
            )
            pct_value = cat.get("pct")
            if not isinstance(pct_value, int):
                continue
            per_category.setdefault(slug, []).append(pct_value)

    if not overall:
        print("error: no grade JSONs with usable overall_pct found.")
        return 1

    out: dict[str, Any] = {
        "version": "0.2",
        "description": args.description
        or f"Aggregated distribution computed from {n} grade JSONs.",
        "n_instances": n,
        "overall": _percentiles(overall),
        "categories": {slug: {"median": _median(pcts)} for slug, pcts in per_category.items()},
    }
    Path(args.output).write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {args.output}: n={n}, "
        f"overall median={out['overall']['median']}%"
    )
    return 0


def _percentiles(values: list[int]) -> dict[str, int]:
    sorted_values = sorted(values)
    if len(sorted_values) < 2:
        v = sorted_values[0]
        return {"median": v, "p25": v, "p75": v}
    # quantiles(n=4, method="inclusive") returns p25, p50, p75 boundaries.
    qs = quantiles(sorted_values, n=4, method="inclusive")
    return {
        "p25": int(round(qs[0])),
        "median": int(round(qs[1])),
        "p75": int(round(qs[2])),
    }


def _median(values: list[int]) -> int:
    sorted_values = sorted(values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[mid]
    return int(round((sorted_values[mid - 1] + sorted_values[mid]) / 2))


if __name__ == "__main__":
    raise SystemExit(main())

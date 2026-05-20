"""Build the AA snapshot fixtures.

Modeled on aa_auto_sdr's JSON output shape (report_suite + dimensions +
metrics + segments + calculated_metrics + classifications).

- aa_snapshot_messy.json: AA implementation with documented issues
  (some missing descriptions, an eVar with conflicting allocation, a
  segment mixing hits/visits/visitors).
- aa_snapshot_clean.json: small, well-governed AA implementation.

Re-run only when fixture properties need to change deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
TOOL_VERSION = "1.0.0"


def _evar(idx: int, *, description: str | None, allocation: str = "most-recent",
          expiration: str = "visit", tags: list[str] | None = None,
          owner_id: int | None = None) -> dict[str, Any]:
    return {
        "id": f"variables/evar{idx}",
        "name": f"eVar {idx}",
        "description": description,
        "type": "string",
        "category": "Custom",
        "tags": tags or [],
        "parent": "",
        "pathable": False,
        "owner_id": owner_id,
        "extra": {"allocation": allocation, "expiration": expiration},
    }


def _prop(idx: int, *, description: str | None,
          tags: list[str] | None = None,
          owner_id: int | None = None) -> dict[str, Any]:
    return {
        "id": f"variables/prop{idx}",
        "name": f"Prop {idx}",
        "description": description,
        "type": "string",
        "category": "Content",
        "tags": tags if tags is not None else ["taxonomy"],
        "parent": "",
        "pathable": True,
        "owner_id": owner_id,
        "extra": {},
    }


def _event(idx: int, *, description: str | None,
           tags: list[str] | None = None,
           owner_id: int | None = None) -> dict[str, Any]:
    return {
        "id": f"metrics/event{idx}",
        "name": f"Event {idx}",
        "description": description,
        "type": "int",
        "category": "Conversion",
        "data_group": "Conversion",
        "tags": tags or [],
        "precision": 0,
        "segmentable": True,
        "owner_id": owner_id,
    }


def build_messy_aa_snapshot() -> dict[str, Any]:
    evars: list[dict[str, Any]] = []
    for i in range(40):
        idx = i + 1
        # 22/40 missing descriptions (55%) — above the calibrated SCH-003
        # strict threshold of 0.35 so the messy fixture actually exercises
        # the rule.
        has_desc = i >= 22
        evars.append(
            _evar(
                idx,
                description=f"eVar {idx} description." if has_desc else None,
                allocation="linear" if i % 7 == 0 else "most-recent",
                expiration="visit" if i % 5 else "visitor",
                tags=["custom"] if i % 3 == 0 else [],
            )
        )

    # 11/20 props missing descriptions, 9/15 events missing — overall ~55%
    # missing-description rate across the messy fixture.
    props = [_prop(i + 1, description=f"Prop {i+1} description." if i >= 11 else None) for i in range(20)]
    events = [_event(i + 1, description="Event description." if i >= 9 else None) for i in range(15)]

    calc_metrics = [
        {
            "id": "cm_conversion_rate",
            "name": "Conversion Rate",
            "description": "Orders / Visits.",
            "type": "decimal",
            "precision": 4,
            "polarity": "positive",
            "tags": [],
            "owner_id": 42,
            "rsid": "messy.prod",
            "categories": ["Conversion"],
            "definition": {"formula": {"func": "divide", "args": ["metrics/orders", "metrics/visits"]}},
            "extra": {},
        },
        {
            "id": "cm_revenue_per_visit",
            "name": "Revenue per Visit",
            "description": None,
            "type": "decimal",
            "precision": 2,
            "polarity": "positive",
            "tags": [],
            "owner_id": 42,
            "rsid": "messy.prod",
            "categories": ["Revenue"],
            "definition": {"formula": {"func": "divide", "args": ["metrics/revenue", "metrics/visits"]}},
            "extra": {},
        },
    ]

    segments = [
        {
            "id": "s_mobile",
            "name": "Mobile Users",
            "description": "Mobile device traffic.",
            "rsid": "messy.prod",
            "owner_id": 42,
            "tags": [],
            "compatibility": {},
            "created": "2025-01-01T00:00:00Z",
            "modified": "2025-06-01T00:00:00Z",
            "definition": {
                "version": [1, 0, 0],
                "container": {"context": "hits", "func": "container", "pred": {"func": "eq", "val": "mobile"}},
            },
            "extra": {},
        },
        {
            "id": "s_returning",
            "name": "Returning Visitors",
            "description": None,
            "rsid": "messy.prod",
            "owner_id": 42,
            "tags": [],
            "compatibility": {},
            "created": None,
            "modified": None,
            "definition": {
                "version": [1, 0, 0],
                "container": {
                    "context": "visitors",
                    "func": "container",
                    "pred": {
                        "func": "and",
                        "args": [
                            {"func": "container", "context": "visits", "pred": {"func": "eq", "val": "v1"}},
                            {"func": "container", "context": "hits", "pred": {"func": "eq", "val": "h1"}},
                        ],
                    },
                },
            },
            "extra": {},
        },
    ]

    classifications = [
        {"id": "ds_campaigns", "name": "Campaign Metadata", "parent": "variables/evar1", "rsid": "messy.prod", "extra": {}},
    ]

    return {
        "report_suite": {
            "rsid": "messy.prod",
            "name": "Messy Production",
            "currency": "USD",
            "parent_rsid": None,
            "timezone": "US/Pacific",
        },
        "captured_at": "2026-04-25T09:14:00+00:00",
        "tool_version": TOOL_VERSION,
        "dimensions": [*evars, *props],
        "metrics": events,
        "calculated_metrics": calc_metrics,
        "segments": segments,
        "classifications": classifications,
        "virtual_report_suites": [],
    }


def build_clean_aa_snapshot() -> dict[str, Any]:
    evars = [
        _evar(i + 1, description=f"Documented eVar {i+1}.", tags=["custom"], owner_id=1)
        for i in range(8)
    ]
    # Props default to tags=["taxonomy"]; preserve so NAME-003 sees a
    # consistent casing pool per tag (props are Title Case under "taxonomy",
    # eVars under "custom").
    props = [
        _prop(i + 1, description=f"Documented Prop {i+1}.", owner_id=1)
        for i in range(5)
    ]
    # Events default to no tags; give them a distinct "event" tag so the
    # clean fixture has no untagged components but NAME-003 still groups
    # them separately from custom eVars / taxonomy props.
    events = [
        _event(i + 1, description=f"Documented event {i+1}.", tags=["event"], owner_id=1)
        for i in range(6)
    ]

    # Five calc metrics, neutral names (no revenue/conversion/order tokens),
    # explicit attribution declared. The last three reference earlier calc
    # metrics + segments so orphan rates land under the 50% thresholds.
    clean_segment_ids = [f"segments/seg_clean_{i+1:02d}" for i in range(8)]
    clean_calc_ids = [f"calculatedMetrics/cm_clean_ratio_{c}" for c in "abcde"]

    # Cross-references collectively reach 4/5 calc metrics and 5/8 segments
    # so CALC-005 / SEG-003 (50% orphan thresholds) stay quiet. Only
    # cm_clean_ratio_e is orphan by design (top-of-graph aggregator).
    calc_specs = [
        ("a", "Metric A / Metric B", ["metrics/event1", "metrics/event2"], []),
        ("b", "Ratio A scaled",      ["metrics/event3", clean_calc_ids[0]], [clean_segment_ids[0]]),
        ("c", "Metric D / Metric E", ["metrics/event4", "metrics/event5"], [clean_segment_ids[1]]),
        ("d", "Ratio C scaled",      ["metrics/event6", clean_calc_ids[2]], [clean_segment_ids[2]]),
        ("e", "Cross blend",         clean_calc_ids[:4],                    clean_segment_ids[3:5]),
    ]
    calc_metrics: list[dict[str, Any]] = []
    for letter, summary, refs, seg_refs in calc_specs:
        formula_args = list(refs) + list(seg_refs)
        calc_metrics.append({
            "id": f"calculatedMetrics/cm_clean_ratio_{letter}",
            "name": f"Clean Ratio {letter.upper()}",
            "description": (
                f"{summary}. Uses linear attribution per documented governance "
                "decision."
            ),
            "type": "decimal",
            "precision": 4,
            "polarity": "positive",
            "tags": ["governance"],
            "owner_id": 1,
            "rsid": "clean.prod",
            "categories": ["Engagement"],
            "attribution": "linear",
            "allocation": "linear",
            "definition": {"formula": {"func": "divide", "args": formula_args}},
            "extra": {},
        })

    # Eight segments, all owned and described. The first three are
    # referenced by calc metrics above so SEG-003 (50% orphan threshold)
    # stays quiet.
    segments = [{
        "id": f"segments/seg_clean_{i+1:02d}",
        "name": f"Clean Segment {i+1:02d}",
        "description": f"Documented shallow segment {i+1:02d}.",
        "rsid": "clean.prod",
        "owner_id": 1,
        "tags": ["governance"],
        "compatibility": {},
        "created": "2025-01-01T00:00:00Z",
        "modified": "2025-01-01T00:00:00Z",
        "definition": {
            "version": [1, 0, 0],
            "container": {
                "context": "hits",
                "func": "container",
                "pred": {"func": "eq", "val": f"value-{i+1}"},
            },
        },
        "extra": {},
    } for i in range(8)]

    return {
        "report_suite": {
            "rsid": "clean.prod",
            "name": "Clean Production",
            "currency": "USD",
            "parent_rsid": None,
            "timezone": "US/Pacific",
        },
        "captured_at": "2026-04-25T09:14:00+00:00",
        "tool_version": TOOL_VERSION,
        # Governance signals — match the CJA clean fixture so out-of-the-box
        # runs grade well without external context attached.
        "metadata": {
            "history_present": True,
            "sdr_doc_present": True,
        },
        "dimensions": [*evars, *props],
        "metrics": events,
        "calculated_metrics": calc_metrics,
        "segments": segments,
        "classifications": [],
        "virtual_report_suites": [],
    }


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURES_DIR / "aa_snapshot_messy.json").write_text(
        json.dumps(build_messy_aa_snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (FIXTURES_DIR / "aa_snapshot_clean.json").write_text(
        json.dumps(build_clean_aa_snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {(FIXTURES_DIR / 'aa_snapshot_messy.json').relative_to(REPO_ROOT)}")
    print(f"Wrote {(FIXTURES_DIR / 'aa_snapshot_clean.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

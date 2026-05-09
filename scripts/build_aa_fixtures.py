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
          expiration: str = "visit", tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": f"variables/evar{idx}",
        "name": f"eVar {idx}",
        "description": description,
        "type": "string",
        "category": "Custom",
        "tags": tags or [],
        "parent": "",
        "pathable": False,
        "extra": {"allocation": allocation, "expiration": expiration},
    }


def _prop(idx: int, *, description: str | None) -> dict[str, Any]:
    return {
        "id": f"variables/prop{idx}",
        "name": f"Prop {idx}",
        "description": description,
        "type": "string",
        "category": "Content",
        "tags": ["taxonomy"],
        "parent": "",
        "pathable": True,
        "extra": {},
    }


def _event(idx: int, *, description: str | None) -> dict[str, Any]:
    return {
        "id": f"metrics/event{idx}",
        "name": f"Event {idx}",
        "description": description,
        "type": "int",
        "category": "Conversion",
        "data_group": "Conversion",
        "tags": [],
        "precision": 0,
        "segmentable": True,
    }


def build_messy_aa_snapshot() -> dict[str, Any]:
    evars: list[dict[str, Any]] = []
    for i in range(40):
        idx = i + 1
        has_desc = i >= 10  # 10/40 missing descriptions
        evars.append(
            _evar(
                idx,
                description=f"eVar {idx} description." if has_desc else None,
                allocation="linear" if i % 7 == 0 else "most-recent",
                expiration="visit" if i % 5 else "visitor",
                tags=["custom"] if i % 3 == 0 else [],
            )
        )

    props = [_prop(i + 1, description=f"Prop {i+1} description." if i % 4 else None) for i in range(20)]
    events = [_event(i + 1, description="Event description." if i % 3 else None) for i in range(15)]

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
    evars = [_evar(i + 1, description="ok", tags=["custom"]) for i in range(8)]
    props = [_prop(i + 1, description="ok") for i in range(5)]
    events = [_event(i + 1, description="ok") for i in range(6)]
    calc_metrics = [{
        "id": "cm_clean_conversion_rate",
        "name": "Clean Conversion Rate",
        "description": "Conversions per visit.",
        "type": "decimal",
        "precision": 4,
        "polarity": "positive",
        "tags": [],
        "owner_id": 1,
        "rsid": "clean.prod",
        "categories": ["Conversion"],
        "definition": {"formula": {"func": "divide", "args": ["metrics/event1", "metrics/event2"]}},
        "extra": {},
    }]
    segments = [{
        "id": "s_clean_mobile",
        "name": "Mobile",
        "description": "Mobile traffic.",
        "rsid": "clean.prod",
        "owner_id": 1,
        "tags": ["governance"],
        "compatibility": {},
        "created": "2025-01-01T00:00:00Z",
        "modified": "2025-01-01T00:00:00Z",
        "definition": {
            "version": [1, 0, 0],
            "container": {"context": "hits", "func": "container", "pred": {"func": "eq", "val": "mobile"}},
        },
        "extra": {},
    }]
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

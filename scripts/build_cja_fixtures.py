"""Build the canonical CJA snapshot fixtures.

Produces two stable goldens used by tests/test_adapters_cja.py and (later)
the rule engine end-to-end tests:

- tests/fixtures/cja_snapshot_messy.json
    487 components total (142 metrics, 203 dimensions, 142 derived fields),
    89 missing descriptions, 4 segments with nesting depth >= 5, 7
    near-duplicate revenue calculated metrics. Mirrors the numbers in the
    sample report fixture (SPEC §3, demo_report.py).

- tests/fixtures/cja_snapshot_clean.json
    A small, well-governed implementation that should grade A: every
    component has a description, segments are shallow, calc metrics are
    distinct.

Re-run only when fixture properties need to change deliberately. The
generated JSON is the test contract; downstream tests (and Phase 3+
end-to-end suites) assert specific counts and IDs against it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

# Stable timestamps — fixtures must be deterministic byte-for-byte.
GEN_TS = "2026-04-25 09:14:00"
BASE_DATE = "2025-09-01T00:00:00Z"
TOOL_VERSION = "3.5.17"

# ---------------------------------------------------------------------------
# Messy fixture builders
# ---------------------------------------------------------------------------


def build_metrics(count: int, missing_descriptions: int) -> list[dict[str, Any]]:
    out = []
    for i in range(count):
        idx = i + 1
        has_desc = i >= missing_descriptions
        out.append({
            "id": f"metrics/cm_metric_{idx:03d}",
            "name": f"Metric {idx:03d}",
            "type": "int" if idx % 3 else "currency",
            "title": f"Metric {idx:03d}",
            "description": f"Auto-generated metric {idx:03d}." if has_desc else "-",
            "dataType": "integer" if idx % 3 else "decimal",
            "precision": 0 if idx % 3 else 2,
            "owner": f"r.kim+{(idx % 5) + 1}@example.com",
            "tags": ["custom"] if idx % 4 == 0 else [],
            "created": BASE_DATE,
            "modified": BASE_DATE,
        })
    return out


def build_dimensions(count: int, missing_descriptions: int) -> list[dict[str, Any]]:
    out = []
    for i in range(count):
        idx = i + 1
        has_desc = i >= missing_descriptions
        out.append({
            "id": f"variables/evar{idx}",
            "name": f"Dimension {idx:03d}",
            "type": "string",
            "title": f"Dimension {idx:03d}",
            "description": f"Auto-generated dimension {idx:03d}." if has_desc else "-",
            "dataType": "string",
            "owner": f"a.patel+{(idx % 7) + 1}@example.com",
            "tags": ["custom"] if idx % 4 == 0 else [],
            "created": BASE_DATE,
            "modified": BASE_DATE,
        })
    return out


def build_derived_fields(count: int) -> dict[str, Any]:
    fields = []
    for i in range(count):
        idx = i + 1
        fields.append({
            "component_id": f"derived/df_field_{idx:03d}",
            "component_name": f"Derived Field {idx:03d}",
            "component_type": "derived_field",
            "description": f"Auto-generated derived field {idx:03d}.",
            "complexity_score": 10.0 + (idx % 30),
            "functions_used": ["concat"],
            "branch_count": 1,
            "nesting_depth": 1 + (idx % 3),
            "operator_count": 1,
            "schema_field_count": 2,
            "schema_fields": [f"schema/field_{idx:03d}"],
            "lookup_references": [],
            "component_references": [],
            "rule_names": [],
            "logic_summary": "concat(a, b)",
            "inferred_output_type": "string",
            "definition_json": json.dumps({"func": "concat", "args": ["a", "b"]}),
            "owner": f"m.chen+{(idx % 3) + 1}@example.com",
            "tags": [],
            "created": BASE_DATE,
            "modified": BASE_DATE,
        })
    return {
        "summary": {
            "data_view_id": "dv_messy_prod_web",
            "total_derived_fields": count,
        },
        "fields": fields,
    }


def build_calculated_metrics() -> dict[str, Any]:
    """30 calc metrics total, 7 of which are near-duplicate revenue formulas."""
    metrics = []

    # 7 near-duplicate revenue calc metrics — matching demo_report's CALC-014 finding.
    revenue_authors = [
        ("cm_revenue_per_visit",       "r.kim@example.com",    "2024-03-12"),
        ("cm_rev_per_visit_v2",        "a.patel@example.com",  "2024-08-04"),
        ("cm_revpv_lasttouch",         "r.kim@example.com",    "2024-11-19"),
        ("cm_rev_visit_linear",        "m.chen@example.com",   "2025-01-22"),
        ("cm_revenue_visit_corrected", "a.patel@example.com",  "2025-04-08"),
        ("cm_rpv_marketing",           "l.gomez@example.com",  "2025-09-15"),
        ("cm_rev_per_visit_final",     "r.kim@example.com",    "2026-02-03"),
    ]
    for mid, owner, created in revenue_authors:
        metrics.append({
            "metric_id": f"calculatedMetrics/{mid}",
            "metric_name": mid.replace("_", " ").title(),
            "description": "Revenue per visit (variant).",
            "owner": owner,
            "owner_id": owner.split("@")[0],
            "approved": True,
            "favorite": False,
            "tags": ["revenue"],
            "created": created + "T00:00:00Z",
            "modified": created + "T00:00:00Z",
            "shares": [],
            "shared_to_count": 0,
            "data_view_id": "dv_messy_prod_web",
            "site_title": "Production Web Analytics",
            "complexity_score": 42.0,
            "functions_used": ["divide"],
            "functions_used_internal": ["divide"],
            "nesting_depth": 2,
            "operator_count": 1,
            "metric_references": ["metrics/revenue", "metrics/visits"],
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": "Revenue / Visits",
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 2,
            "definition_json": json.dumps({
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/revenue"},
                "col2": {"func": "metric", "name": "metrics/visits"},
            }),
        })

    # 23 distinct calc metrics — varied formulas, governance, complexity.
    distinct_specs = [
        ("cm_orders_per_visit",       "Orders / Visits",       1, ["metrics/orders", "metrics/visits"]),
        ("cm_avg_order_value",        "Revenue / Orders",      1, ["metrics/revenue", "metrics/orders"]),
        ("cm_bounce_rate_filtered",   "Bounces / Visits",      2, ["metrics/bounces", "metrics/visits"]),
        ("cm_engagement_rate",        "Engaged / Visits",      2, ["metrics/engaged", "metrics/visits"]),
        ("cm_signup_conversion",      "Signups / Visits",      1, ["metrics/signups", "metrics/visits"]),
        ("cm_paid_ratio",             "Paid Visits / Visits",  2, ["metrics/paid_visits", "metrics/visits"]),
        ("cm_organic_share",          "Organic / Visits",      2, ["metrics/organic", "metrics/visits"]),
        ("cm_repeat_buyer_rate",      "Repeat / Buyers",       2, ["metrics/repeat", "metrics/buyers"]),
        ("cm_cart_to_order",          "Orders / Carts",        2, ["metrics/orders", "metrics/carts"]),
        ("cm_search_to_view",         "Views / Searches",      2, ["metrics/views", "metrics/searches"]),
        ("cm_video_completion",       "Completes / Starts",    1, ["metrics/completes", "metrics/starts"]),
        ("cm_email_ctr",              "Clicks / Sends",        1, ["metrics/clicks", "metrics/sends"]),
        ("cm_form_submit_rate",       "Submits / Form Views",  2, ["metrics/submits", "metrics/form_views"]),
        ("cm_promo_redemption",       "Redeem / Impressions",  2, ["metrics/redeems", "metrics/impressions"]),
        ("cm_help_resolution",        "Resolved / Tickets",    1, ["metrics/resolved", "metrics/tickets"]),
        ("cm_pages_per_visit",        "Pageviews / Visits",    1, ["metrics/pageviews", "metrics/visits"]),
        ("cm_active_user_rate",       "Active / Users",        2, ["metrics/active", "metrics/users"]),
        ("cm_returning_share",        "Returning / Users",     2, ["metrics/returning", "metrics/users"]),
        ("cm_revenue_b2b",            "Revenue B2B / Visits",  3, ["metrics/revenue_b2b", "metrics/visits"]),
        ("cm_loyalty_revenue",        "Loyalty Rev / Members", 3, ["metrics/loyalty_rev", "metrics/members"]),
        ("cm_apac_share",             "APAC Visits / Visits",  2, ["metrics/apac_visits", "metrics/visits"]),
        ("cm_emea_share",             "EMEA Visits / Visits",  2, ["metrics/emea_visits", "metrics/visits"]),
        ("cm_amer_share",             "AMER Visits / Visits",  2, ["metrics/amer_visits", "metrics/visits"]),
    ]
    for i, (mid, summary, nesting, refs) in enumerate(distinct_specs):
        metrics.append({
            "metric_id": f"calculatedMetrics/{mid}",
            "metric_name": mid.replace("_", " ").title(),
            "description": f"Distinct calculated metric: {summary}.",
            "owner": f"team{(i % 4) + 1}@example.com",
            "owner_id": f"team{(i % 4) + 1}",
            "approved": (i % 3) != 0,
            "favorite": False,
            "tags": [] if i % 5 else ["governance"],
            "created": "2024-06-01T00:00:00Z",
            "modified": "2025-06-01T00:00:00Z",
            "shares": [],
            "shared_to_count": 0,
            "data_view_id": "dv_messy_prod_web",
            "site_title": "Production Web Analytics",
            "complexity_score": 25.0 + i,
            "functions_used": ["divide"],
            "functions_used_internal": ["divide"],
            "nesting_depth": nesting,
            "operator_count": 1,
            "metric_references": refs,
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": summary,
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 2,
            "definition_json": json.dumps({
                "func": "divide",
                "col1": {"func": "metric", "name": refs[0]},
                "col2": {"func": "metric", "name": refs[1]},
            }),
        })

    return {
        "summary": {
            "data_view_id": "dv_messy_prod_web",
            "data_view_name": "Production Web Analytics",
            "total_calculated_metrics": len(metrics),
        },
        "metrics": metrics,
    }


def build_segments() -> dict[str, Any]:
    """25 segments total, 4 with nesting depth >= 5 (depths 8, 6, 6, 5)."""
    deep_specs = [
        ("seg_qualified_lead_v3",       8, ["event", "session", "person"]),
        ("seg_high_intent_returning",   6, ["session", "event"]),
        ("seg_b2b_account_engaged",     6, ["event", "session"]),
        ("seg_promo_responsive",        5, ["event"]),
    ]
    segments = []
    for sid, depth, contexts in deep_specs:
        segments.append({
            "segment_id": f"segments/{sid}",
            "segment_name": sid.replace("_", " ").title(),
            "description": f"Deeply nested segment: {sid} (depth {depth}).",
            "owner": "r.kim@example.com",
            "owner_id": "r.kim",
            "approved": True,
            "favorite": False,
            "tags": ["governance"],
            "created": "2024-01-15T00:00:00Z",
            "modified": "2025-12-01T00:00:00Z",
            "shares": [],
            "shared_to_count": 0,
            "data_view_id": "dv_messy_prod_web",
            "site_title": "Production Web Analytics",
            "complexity_score": 60.0 + depth,
            "container_type": contexts[0],
            "functions_used": ["container", "and", "or"],
            "functions_used_internal": ["container", "and", "or"],
            "predicate_count": 4,
            "logic_operator_count": 3,
            "nesting_depth": depth,
            "container_count": len(contexts),
            "dimension_references": [f"variables/evar{(i + 1)}" for i in range(3)],
            "metric_references": ["metrics/cm_metric_001"],
            "other_segment_references": [],
            "definition_summary": f"complex {' / '.join(contexts)}-level conditions",
            "definition_json": json.dumps(
                _build_nested_segment_definition(depth, contexts)
            ),
        })

    # 21 shallow segments
    for i in range(21):
        idx = i + 1
        segments.append({
            "segment_id": f"segments/seg_simple_{idx:03d}",
            "segment_name": f"Simple Segment {idx:03d}",
            "description": f"Single-condition segment {idx:03d}.",
            "owner": f"team{(idx % 4) + 1}@example.com",
            "owner_id": f"team{(idx % 4) + 1}",
            "approved": True,
            "favorite": False,
            "tags": [],
            "created": "2024-04-01T00:00:00Z",
            "modified": "2025-04-01T00:00:00Z",
            "shares": [],
            "shared_to_count": 0,
            "data_view_id": "dv_messy_prod_web",
            "site_title": "Production Web Analytics",
            "complexity_score": 5.0 + idx,
            "container_type": "event",
            "functions_used": ["container", "streq"],
            "functions_used_internal": ["container", "streq"],
            "predicate_count": 1,
            "logic_operator_count": 0,
            "nesting_depth": 2,
            "container_count": 1,
            "dimension_references": [f"variables/evar{(idx % 30) + 1}"],
            "metric_references": [],
            "other_segment_references": [],
            "definition_summary": "single equality on event",
            "definition_json": json.dumps({
                "func": "container",
                "context": "event",
                "pred": {"func": "streq", "val": {"func": "attr", "name": f"variables/evar{(idx % 30) + 1}"}, "str": "match"},
            }),
        })

    return {
        "summary": {
            "data_view_id": "dv_messy_prod_web",
            "data_view_name": "Production Web Analytics",
            "total_segments": len(segments),
        },
        "segments": segments,
    }


def _build_nested_segment_definition(depth: int, contexts: list[str]) -> dict[str, Any]:
    """Build a synthetic segment definition with the requested nesting depth.

    Alternates container contexts down the tree so segment-mixing rules can
    later detect heterogeneous container chains.
    """
    chain_contexts = [contexts[i % len(contexts)] for i in range(depth)]
    inner: dict[str, Any] = {
        "func": "streq",
        "val": {"func": "attr", "name": "variables/evar1"},
        "str": "match",
    }
    for ctx in reversed(chain_contexts):
        inner = {"func": "container", "context": ctx, "pred": inner}
    return inner


# ---------------------------------------------------------------------------
# Clean fixture
# ---------------------------------------------------------------------------


def build_clean_snapshot() -> dict[str, Any]:
    metrics = [{
        "id": f"metrics/cm_clean_metric_{i+1:02d}",
        "name": f"Clean Metric {i+1:02d}",
        "type": "int",
        "title": f"Clean Metric {i+1:02d}",
        "description": f"Documented metric {i+1:02d}.",
        "dataType": "integer",
        "precision": 0,
        "owner": "owner@example.com",
        "tags": ["custom"],
        "created": BASE_DATE,
        "modified": BASE_DATE,
    } for i in range(12)]

    dimensions = [{
        "id": f"variables/evar{i+1}",
        "name": f"Clean Dimension {i+1:02d}",
        "type": "string",
        "title": f"Clean Dimension {i+1:02d}",
        "description": f"Documented dimension {i+1:02d}.",
        "dataType": "string",
        "owner": "owner@example.com",
        "tags": ["custom"],
        "created": BASE_DATE,
        "modified": BASE_DATE,
    } for i in range(18)]

    derived = [{
        "component_id": f"derived/df_clean_{i+1:02d}",
        "component_name": f"Clean Derived {i+1:02d}",
        "component_type": "derived_field",
        "description": f"Documented derived field {i+1:02d}.",
        "complexity_score": 10.0,
        "functions_used": ["concat"],
        "branch_count": 1,
        "nesting_depth": 1,
        "operator_count": 1,
        "schema_field_count": 1,
        "schema_fields": [f"schema/clean_{i+1}"],
        "lookup_references": [],
        "component_references": [],
        "rule_names": [],
        "logic_summary": "concat(a, b)",
        "inferred_output_type": "string",
        "definition_json": json.dumps({"func": "concat", "args": ["a", "b"]}),
        "owner": "owner@example.com",
        "tags": ["custom"],
        "created": BASE_DATE,
        "modified": BASE_DATE,
    } for i in range(10)]

    calc_metrics = []
    for i, (mid, summary, refs) in enumerate([
        ("cm_clean_orders_per_visit",   "Orders / Visits",   ["metrics/orders", "metrics/visits"]),
        ("cm_clean_avg_order_value",    "Revenue / Orders",  ["metrics/revenue", "metrics/orders"]),
        ("cm_clean_bounce_rate",        "Bounces / Visits",  ["metrics/bounces", "metrics/visits"]),
        ("cm_clean_signup_rate",        "Signups / Visits",  ["metrics/signups", "metrics/visits"]),
        ("cm_clean_engagement_rate",    "Engaged / Visits",  ["metrics/engaged", "metrics/visits"]),
    ]):
        calc_metrics.append({
            "metric_id": f"calculatedMetrics/{mid}",
            "metric_name": mid.replace("_", " ").title(),
            "description": f"Documented metric: {summary}.",
            "owner": "owner@example.com",
            "owner_id": "owner",
            "approved": True,
            "favorite": False,
            "tags": ["governance", "custom"],
            "created": BASE_DATE,
            "modified": BASE_DATE,
            "shares": [],
            "shared_to_count": 0,
            "data_view_id": "dv_clean_prod_web",
            "site_title": "Clean Production Web Analytics",
            "complexity_score": 15.0 + i,
            "functions_used": ["divide"],
            "functions_used_internal": ["divide"],
            "nesting_depth": 1,
            "operator_count": 1,
            "metric_references": refs,
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": summary,
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 2,
            "definition_json": json.dumps({
                "func": "divide",
                "col1": {"func": "metric", "name": refs[0]},
                "col2": {"func": "metric", "name": refs[1]},
            }),
        })

    segments = []
    for i in range(8):
        segments.append({
            "segment_id": f"segments/seg_clean_{i+1:02d}",
            "segment_name": f"Clean Segment {i+1:02d}",
            "description": f"Documented shallow segment {i+1:02d}.",
            "owner": "owner@example.com",
            "owner_id": "owner",
            "approved": True,
            "favorite": False,
            "tags": ["governance"],
            "created": BASE_DATE,
            "modified": BASE_DATE,
            "shares": [],
            "shared_to_count": 0,
            "data_view_id": "dv_clean_prod_web",
            "site_title": "Clean Production Web Analytics",
            "complexity_score": 8.0,
            "container_type": "event",
            "functions_used": ["container", "streq"],
            "functions_used_internal": ["container", "streq"],
            "predicate_count": 1,
            "logic_operator_count": 0,
            "nesting_depth": 2,
            "container_count": 1,
            "dimension_references": [f"variables/evar{i + 1}"],
            "metric_references": [],
            "other_segment_references": [],
            "definition_summary": "single equality on event",
            "definition_json": json.dumps({
                "func": "container",
                "context": "event",
                "pred": {"func": "streq", "val": {"func": "attr", "name": f"variables/evar{i + 1}"}, "str": "match"},
            }),
        })

    return {
        "metadata": {
            "Generation Timestamp": GEN_TS,
            "Data View ID": "dv_clean_prod_web",
            "Data View Name": "Clean Production Web Analytics",
            "Total Metrics": len(metrics),
            "Total Dimensions": len(dimensions),
            "Tool Version": TOOL_VERSION,
        },
        "data_view": {
            "data_view_id": "dv_clean_prod_web",
            "data_view_name": "Clean Production Web Analytics",
        },
        "metrics": metrics,
        "dimensions": dimensions,
        "data_quality": [],
        "derived_fields": {
            "summary": {"data_view_id": "dv_clean_prod_web", "total_derived_fields": len(derived)},
            "fields": derived,
        },
        "calculated_metrics": {
            "summary": {
                "data_view_id": "dv_clean_prod_web",
                "total_calculated_metrics": len(calc_metrics),
            },
            "metrics": calc_metrics,
        },
        "segments": {
            "summary": {
                "data_view_id": "dv_clean_prod_web",
                "total_segments": len(segments),
            },
            "segments": segments,
        },
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def build_messy_snapshot() -> dict[str, Any]:
    metrics = build_metrics(count=142, missing_descriptions=38)
    dimensions = build_dimensions(count=203, missing_descriptions=51)
    derived = build_derived_fields(count=142)
    calc_metrics = build_calculated_metrics()
    segments = build_segments()

    return {
        "metadata": {
            "Generation Timestamp": GEN_TS,
            "Data View ID": "dv_messy_prod_web",
            "Data View Name": "Production Web Analytics",
            "Total Metrics": len(metrics),
            "Total Dimensions": len(dimensions),
            "Tool Version": TOOL_VERSION,
        },
        "data_view": {
            "data_view_id": "dv_messy_prod_web",
            "data_view_name": "Production Web Analytics",
        },
        "metrics": metrics,
        "dimensions": dimensions,
        "data_quality": [],
        "derived_fields": derived,
        "calculated_metrics": calc_metrics,
        "segments": segments,
    }


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    messy_path = FIXTURES_DIR / "cja_snapshot_messy.json"
    clean_path = FIXTURES_DIR / "cja_snapshot_clean.json"

    messy_path.write_text(
        json.dumps(build_messy_snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    clean_path.write_text(
        json.dumps(build_clean_snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {messy_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {clean_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

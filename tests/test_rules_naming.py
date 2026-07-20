"""Tests for rules/checks/naming.py (NAME-001..NAME-004)."""

from __future__ import annotations

from typing import Any

from sdr_grader.core.models import CalculatedMetric, Component, Implementation, Segment
from sdr_grader.rules.checks.naming import (
    _classify_casing,
    _target_display,
    check_casing_consistency,
    check_prefix_consistency,
    check_regex_match_id,
    check_semantic_consistency,
)
from sdr_grader.rules.engine import RuleContext


def _component(
    idx: int,
    *,
    comp_type: str = "dimension",
    name: str | None = None,
    cid: str | None = None,
    tags: list[str] | None = None,
) -> Component:
    return Component(
        id=cid or f"variables/evar{idx}",
        name=name or f"Custom Dimension {idx:02d}",
        description="ok",
        component_type=comp_type,  # type: ignore[arg-type]
        data_type="string",
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=None,
        tags=tags or [],
    )


def _impl(
    *,
    metrics: list[Component] | None = None,
    dimensions: list[Component] | None = None,
    segments: list[Segment] | None = None,
    calculated_metrics: list[CalculatedMetric] | None = None,
) -> Implementation:
    return Implementation(
        platform="cja",
        instance_id="dv_test",
        instance_name="Test",
        snapshot_taken_at=None,
        snapshot_source="t",
        adapter_version="0",
        metrics=metrics or [],
        dimensions=dimensions or [],
        segments=segments or [],
        calculated_metrics=calculated_metrics or [],
        derived_fields=[],
        raw={},
    )


def _ctx(rule_id: str, **params: Any) -> RuleContext:
    return RuleContext(
        rule_id=rule_id,
        rule_name=rule_id,
        severity="low",
        category="naming_consistency",
        platforms=["cja", "aa"],
        params=params,
    )


# ---------------------------------------------------------------------------
# NAME-001 prefix consistency
# ---------------------------------------------------------------------------


def test_prefix_consistency_skips_pool_smaller_than_five():
    dims = [_component(i, cid=f"variables/c_{i}", tags=["custom"]) for i in range(3)]
    findings = check_prefix_consistency(
        _impl(dimensions=dims), _ctx("NAME-001", target="dimensions", tag_filter="custom")
    )
    assert findings == []


def test_prefix_consistency_passes_when_all_share_prefix():
    dims = [_component(i, cid=f"variables/c_dim_{i}", tags=["custom"]) for i in range(20)]
    findings = check_prefix_consistency(
        _impl(dimensions=dims),
        _ctx("NAME-001", target="dimensions", tag_filter="custom", min_consistency=0.80),
    )
    assert findings == []


def test_prefix_consistency_fires_below_threshold():
    dims = [_component(i, cid=f"variables/c_dim_{i}", tags=["custom"]) for i in range(15)]
    dims += [
        _component(50 + i, cid=f"variables/x_dim_{i}", tags=["custom"]) for i in range(5)
    ]  # 25% outliers
    findings = check_prefix_consistency(
        _impl(dimensions=dims),
        _ctx("NAME-001", target="dimensions", tag_filter="custom", min_consistency=0.80),
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.id == "NAME-001"
    assert "75% of custom dimensions" in finding.body[0].html
    assert "c_" in finding.body[0].html


def test_prefix_consistency_filters_by_tag():
    dims = [_component(i, cid=f"variables/c_d_{i}", tags=["custom"]) for i in range(10)]
    dims += [
        _component(100 + i, cid=f"variables/native_{i}") for i in range(5)
    ]  # untagged, ignored
    findings = check_prefix_consistency(
        _impl(dimensions=dims),
        _ctx("NAME-001", target="dimensions", tag_filter="custom", min_consistency=0.80),
    )
    assert findings == []


# ---------------------------------------------------------------------------
# NAME-002 regex_match_id
# ---------------------------------------------------------------------------


def test_regex_match_id_passes_when_all_ids_compliant():
    dims = [_component(i, cid=f"variables/dim_{i}") for i in range(5)]
    findings = check_regex_match_id(
        _impl(dimensions=dims), _ctx("NAME-002", targets=["dimensions"])
    )
    assert findings == []


def test_regex_match_id_fires_on_whitespace_id():
    dims = [
        _component(1, cid="variables/good_id"),
        _component(2, cid="variables/bad id with spaces"),
        _component(3, cid="variables/another bad@one"),
    ]
    findings = check_regex_match_id(
        _impl(dimensions=dims), _ctx("NAME-002", targets=["dimensions"])
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.id == "NAME-002"
    assert finding.title.startswith("2 IDs")
    assert "bad id with spaces" in finding.body[1].items[0]


def test_regex_match_id_uses_default_pattern_when_omitted():
    dims = [_component(1, cid="variables/with space")]
    findings = check_regex_match_id(
        _impl(dimensions=dims), _ctx("NAME-002", targets=["dimensions"])
    )
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# NAME-003 casing consistency
# ---------------------------------------------------------------------------


def test_casing_consistency_passes_when_uniform():
    dims = [_component(i, name=f"Dimension {i:02d}", tags=["custom"]) for i in range(10)]
    findings = check_casing_consistency(
        _impl(dimensions=dims),
        _ctx("NAME-003", target="dimensions", tag_filter="custom", min_consistency=0.80),
    )
    assert findings == []


def test_casing_consistency_fires_on_mixed_styles():
    dims = [_component(i, name=f"camelCaseName{i}", tags=["custom"]) for i in range(15)]
    dims += [_component(50 + i, name=f"snake_case_{i}", tags=["custom"]) for i in range(5)]
    findings = check_casing_consistency(
        _impl(dimensions=dims),
        _ctx("NAME-003", target="dimensions", tag_filter="custom", min_consistency=0.80),
    )
    assert len(findings) == 1
    assert findings[0].id == "NAME-003"


def test_casing_consistency_skips_small_or_unclassifiable_pools():
    small = [_component(i, name=f"camelCase{i}") for i in range(4)]
    assert (
        check_casing_consistency(
            _impl(dimensions=small),
            _ctx("NAME-003", target="dimensions"),
        )
        == []
    )

    unclassifiable = [_component(i, name=str(10000 + i)) for i in range(5)]
    assert (
        check_casing_consistency(
            _impl(dimensions=unclassifiable),
            _ctx("NAME-003", target="dimensions"),
        )
        == []
    )


def test_casing_helpers_cover_supported_styles_and_display_fallbacks():
    assert _classify_casing("") is None
    assert _classify_casing("   ") is None
    assert _classify_casing("PascalCase") == "PascalCase"
    assert _classify_casing("snake_case") == "snake_case"
    assert _classify_casing("kebab-case") == "kebab-case"
    assert _classify_casing("SCREAMING_SNAKE") == "SCREAMING_SNAKE"
    assert _classify_casing("12345") is None
    assert _target_display("custom_targets", None) == "custom targets"


# ---------------------------------------------------------------------------
# NAME-004 semantic_consistency
# ---------------------------------------------------------------------------


def test_semantic_consistency_passes_with_one_synonym_only():
    dims = [_component(i, name=f"User attribute {i}") for i in range(5)]
    findings = check_semantic_consistency(_impl(dimensions=dims), _ctx("NAME-004"))
    assert findings == []


def test_semantic_consistency_fires_when_synonyms_overlap():
    dims = [
        _component(1, name="User segment", cid="variables/user_segment"),
        _component(2, name="Visitor age", cid="variables/visitor_age"),
        _component(3, name="Page views", cid="variables/page_views"),
        _component(4, name="Screen views", cid="variables/screen_views"),
    ]
    findings = check_semantic_consistency(_impl(dimensions=dims), _ctx("NAME-004"))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.id == "NAME-004"
    assert "user, visitor" in str(finding.body[1].items)
    assert "page, screen" in str(finding.body[1].items)


def test_semantic_consistency_accepts_custom_synonym_groups():
    dims = [_component(1, name="customer cohort"), _component(2, name="member tier")]
    findings = check_semantic_consistency(
        _impl(dimensions=dims),
        _ctx("NAME-004", synonym_groups=[["customer", "member"]]),
    )
    assert len(findings) == 1


def test_semantic_consistency_default_groups_catch_adobe_domain_mismatches():
    """The May 2026 rubric audit added four Adobe-domain pairs to the
    default synonym list. Each pair should fire when its terms coexist."""
    cases = [
        ("Revenue per Visit", "Sales per Visit", ("revenue", "sales")),
        ("Cart Adds", "Basket Adds", ("cart", "basket")),
        ("Order Total", "Transaction Total", ("order", "transaction")),
        ("Purchase Completion", "Checkout Completion", ("purchase", "checkout")),
    ]
    for name_a, name_b, (term_a, term_b) in cases:
        dims = [
            _component(1, name=name_a, cid=f"variables/{name_a.lower().replace(' ', '_')}"),
            _component(2, name=name_b, cid=f"variables/{name_b.lower().replace(' ', '_')}"),
        ]
        findings = check_semantic_consistency(_impl(dimensions=dims), _ctx("NAME-004"))
        assert len(findings) == 1, f"expected one finding for {name_a!r} vs {name_b!r}"
        items_text = " ".join(" ".join(b.items or []) for b in findings[0].body if b.items)
        assert term_a in items_text and term_b in items_text, (
            f"expected both {term_a!r} and {term_b!r} in finding items "
            f"for {name_a!r} vs {name_b!r}; got: {items_text}"
        )


def test_semantic_consistency_event_and_conversion_NOT_in_defaults():
    """`event/conversion` was deliberately excluded from the defaults — `event`
    is an AA platform primitive that legitimately coexists with `conversion`
    in component names. A snapshot using both must not fire NAME-004."""
    dims = [
        _component(1, name="Custom Event Type", cid="variables/event_type"),
        _component(2, name="Conversion Rate", cid="metrics/conversion_rate"),
    ]
    findings = check_semantic_consistency(_impl(dimensions=dims), _ctx("NAME-004"))
    assert findings == []

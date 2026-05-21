"""Tests for governance rules (GOV-001..GOV-006)."""

from __future__ import annotations

from _rule_test_helpers import component, ctx, impl
from sdr_grader.rules.checks.governance import (
    check_doc_drift,
    check_missing_owners,
    check_missing_tags,
    check_sdr_doc_absent,
    check_snapshot_age,
    check_snapshot_history_absent,
)

# ---------------------------------------------------------------------------
# GOV-001 snapshot history
# ---------------------------------------------------------------------------


def test_history_fires_when_no_signal():
    findings = check_snapshot_history_absent(impl(), ctx("GOV-001", category="governance_posture"))
    assert len(findings) == 1
    assert findings[0].id == "GOV-001"


def test_history_quiet_when_param_signals_present():
    findings = check_snapshot_history_absent(
        impl(),
        ctx("GOV-001", category="governance_posture", history_present=True),
    )
    assert findings == []


def test_history_quiet_when_metadata_signals_present():
    findings = check_snapshot_history_absent(
        impl(raw={"metadata": {"history_present": True}}),
        ctx("GOV-001", category="governance_posture"),
    )
    assert findings == []


def test_history_param_overrides_metadata():
    """Pack-level params win over snapshot metadata."""
    findings = check_snapshot_history_absent(
        impl(raw={"metadata": {"history_present": True}}),
        ctx("GOV-001", category="governance_posture", history_present=False),
    )
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# GOV-002 snapshot age
# ---------------------------------------------------------------------------


def test_age_no_op_without_reference_date():
    findings = check_snapshot_age(
        impl(), ctx("GOV-002", category="governance_posture", max_age_days=90)
    )
    assert findings == []


def test_age_fires_when_snapshot_older_than_max():
    impl_obj = impl()
    impl_obj.__dict__["snapshot_taken_at"] = "2025-01-01"  # tolerated since dataclass not frozen
    findings = check_snapshot_age(
        impl_obj,
        ctx("GOV-002", category="governance_posture", max_age_days=30, reference_date="2025-06-01"),
    )
    assert len(findings) == 1
    assert "151 days old" in findings[0].title


def test_age_quiet_when_snapshot_within_window():
    impl_obj = impl()
    impl_obj.__dict__["snapshot_taken_at"] = "2025-05-25"
    findings = check_snapshot_age(
        impl_obj,
        ctx("GOV-002", category="governance_posture", max_age_days=30, reference_date="2025-06-01"),
    )
    assert findings == []


# ---------------------------------------------------------------------------
# GOV-003 SDR doc absent
# ---------------------------------------------------------------------------


def test_sdr_fires_when_no_signal():
    findings = check_sdr_doc_absent(impl(), ctx("GOV-003", category="governance_posture"))
    assert len(findings) == 1


def test_sdr_quiet_when_metadata_signals_present():
    findings = check_sdr_doc_absent(
        impl(raw={"metadata": {"sdr_doc_present": True}}),
        ctx("GOV-003", category="governance_posture"),
    )
    assert findings == []


# ---------------------------------------------------------------------------
# GOV-004 missing owners
# ---------------------------------------------------------------------------


def test_missing_owners_quiet_under_threshold():
    metrics = [component(i, owner="owner") for i in range(95)]
    metrics += [component(i, owner=None) for i in range(5)]  # 5 / 100 = 5%
    findings = check_missing_owners(
        impl(metrics=metrics),
        ctx("GOV-004", category="governance_posture", threshold=0.10),
    )
    assert findings == []


def test_missing_owners_fires_above_threshold():
    metrics = [component(i, owner="owner") for i in range(80)]
    metrics += [component(i, owner=None) for i in range(20)]  # 20%
    findings = check_missing_owners(
        impl(metrics=metrics),
        ctx("GOV-004", category="governance_posture", threshold=0.10),
    )
    assert len(findings) == 1
    assert "20 components lack owner" in findings[0].title


# ---------------------------------------------------------------------------
# GOV-005 missing tags
# ---------------------------------------------------------------------------


def test_missing_tags_quiet_under_threshold():
    metrics = [component(i, tags=["custom"]) for i in range(60)]
    metrics += [component(i) for i in range(40)]  # 40% untagged
    findings = check_missing_tags(
        impl(metrics=metrics),
        ctx("GOV-005", category="governance_posture", threshold=0.50),
    )
    assert findings == []


def test_missing_tags_fires_when_majority_untagged():
    metrics = [component(i, tags=["custom"]) for i in range(20)]
    metrics += [component(i) for i in range(80)]
    findings = check_missing_tags(
        impl(metrics=metrics),
        ctx("GOV-005", category="governance_posture", threshold=0.50),
    )
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# GOV-006 doc drift (stub)
# ---------------------------------------------------------------------------


def test_doc_drift_is_no_op_without_sdr_date():
    """Without any source of the last-SDR-updated date, the rule must
    no-op rather than false-fire on every snapshot."""
    assert check_doc_drift(impl(), ctx("GOV-006", category="governance_posture")) == []


def test_doc_drift_fires_when_components_modified_after_last_sdr_update():
    """Modified-after-doc components above the threshold rate must fire,
    and the finding must list the drifted IDs."""
    modified_recently = component(1, name="Recently Touched")
    modified_recently.modified_at = "2026-04-15T00:00:00Z"
    modified_old = component(2, name="Old, Unchanged")
    modified_old.modified_at = "2025-01-01T00:00:00Z"
    i = impl(metrics=[modified_recently, modified_old])

    findings = check_doc_drift(
        i,
        ctx(
            "GOV-006",
            category="governance_posture",
            last_sdr_update_at="2026-01-01",
            threshold=0.10,
        ),
    )
    assert len(findings) == 1
    f = findings[0]
    assert "1 components modified" in f.title
    # Drifted component ID must appear in the components block.
    items = []
    for block in f.body:
        items.extend(block.items or [])
    assert any("m_001" in s for s in items)


def test_doc_drift_silent_when_rate_below_threshold():
    """Most components untouched, only 1 in 10 modified → below 20%
    threshold, rule stays silent."""
    components = [component(i) for i in range(10)]
    components[0].modified_at = "2026-04-15T00:00:00Z"
    for c in components[1:]:
        c.modified_at = "2024-01-01T00:00:00Z"
    i = impl(metrics=components)

    findings = check_doc_drift(
        i,
        ctx(
            "GOV-006",
            category="governance_posture",
            last_sdr_update_at="2026-01-01",
            threshold=0.20,
        ),
    )
    assert findings == []


def test_doc_drift_reads_sdr_date_from_supplementary_data():
    """When ctx.params doesn't carry the date, the rule falls back to
    supplementary_data['sdr']['last_updated_at']."""
    c = component(1)
    c.modified_at = "2026-04-15T00:00:00Z"
    i = impl(metrics=[c])
    i.supplementary_data["sdr"] = {"last_updated_at": "2026-01-01T00:00:00Z"}

    findings = check_doc_drift(i, ctx("GOV-006", category="governance_posture", threshold=0.10))
    assert len(findings) == 1


def test_doc_drift_silent_on_unparseable_sdr_date():
    """Garbage in last_sdr_update_at must be tolerated as no-op rather
    than crashing the run."""
    c = component(1)
    c.modified_at = "2026-04-15T00:00:00Z"
    findings = check_doc_drift(
        impl(metrics=[c]),
        ctx(
            "GOV-006",
            category="governance_posture",
            last_sdr_update_at="not-a-date",
        ),
    )
    assert findings == []


def test_doc_drift_silent_when_no_components():
    """Empty implementation can't drift from anything; no-op."""
    findings = check_doc_drift(
        impl(),
        ctx(
            "GOV-006",
            category="governance_posture",
            last_sdr_update_at="2026-01-01",
        ),
    )
    assert findings == []

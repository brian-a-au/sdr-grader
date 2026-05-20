"""Tests for segment_complexity rules (SEG-002..SEG-007)."""

from __future__ import annotations

from _rule_test_helpers import calc, ctx, impl, segment
from sdr_grader.rules.checks.segments import (
    check_circular_segments,
    check_container_mixing,
    check_duplicate_segments,
    check_orphan_segments,
    check_segment_nesting_depth,
    check_segments_missing_descriptions,
)


# SEG-002
def test_container_mixing_fires_on_multi_context_segment():
    segs = [
        segment("segments/clean", container_types=["event"]),
        segment("segments/mixed", container_types=["event", "session"]),
    ]
    findings = check_container_mixing(impl(segments=segs), ctx("SEG-002"))
    assert len(findings) == 1
    assert "1 segment" in findings[0].title


def test_container_mixing_quiet_when_homogeneous():
    segs = [segment(f"segments/s_{i}", container_types=["event"]) for i in range(3)]
    findings = check_container_mixing(impl(segments=segs), ctx("SEG-002"))
    assert findings == []


# SEG-003
def test_orphan_segments_quiet_when_referenced():
    segs = [segment(f"segments/s_{i}") for i in range(10)]
    # 7 segments referenced -> 30% orphan rate, well under 50%.
    referencing_calc = [
        calc("calculatedMetrics/c", references=[s.id for s in segs[:7]])
    ]
    findings = check_orphan_segments(
        impl(segments=segs, calc=referencing_calc),
        ctx("SEG-003", threshold=0.50),
    )
    assert findings == []


def test_orphan_segments_fires_when_majority_orphan():
    segs = [segment(f"segments/s_{i}") for i in range(10)]
    findings = check_orphan_segments(impl(segments=segs), ctx("SEG-003", threshold=0.50))
    assert len(findings) == 1


# SEG-004
def test_circular_segments_detected():
    segs = [
        segment("segments/a", references=["segments/b"]),
        segment("segments/b", references=["segments/c"]),
        segment("segments/c", references=["segments/a"]),
    ]
    findings = check_circular_segments(impl(segments=segs), ctx("SEG-004"))
    assert len(findings) == 1
    assert "1 circular" in findings[0].title


def test_circular_segments_quiet_in_DAG():
    segs = [
        segment("segments/a", references=["segments/b"]),
        segment("segments/b", references=["segments/c"]),
        segment("segments/c"),
    ]
    findings = check_circular_segments(impl(segments=segs), ctx("SEG-004"))
    assert findings == []


# SEG-005
def test_segments_missing_descriptions_fires():
    segs = [segment(f"segments/s_{i}", description=None) for i in range(7)]
    segs += [segment(f"segments/s_{i+7}", description="ok") for i in range(3)]
    findings = check_segments_missing_descriptions(
        impl(segments=segs), ctx("SEG-005", threshold=0.30),
    )
    assert len(findings) == 1


def test_segments_missing_descriptions_quiet_under_threshold():
    segs = [segment(f"segments/s_{i}", description="ok") for i in range(8)]
    segs += [segment(f"segments/s_{i+8}", description=None) for i in range(2)]
    findings = check_segments_missing_descriptions(
        impl(segments=segs), ctx("SEG-005", threshold=0.30),
    )
    assert findings == []


# SEG-006
def test_duplicate_segments_fires_on_identical_definition():
    segs = [
        segment("segments/a", definition={"func": "container", "context": "event"}),
        segment("segments/b", definition={"func": "container", "context": "event"}),
        segment("segments/c", definition={"func": "container", "context": "session"}),
    ]
    findings = check_duplicate_segments(impl(segments=segs), ctx("SEG-006"))
    assert len(findings) == 1


def test_duplicate_segments_quiet_when_unique():
    segs = [
        segment("segments/a", definition={"func": "container", "context": "event"}),
        segment("segments/b", definition={"func": "container", "context": "session"}),
    ]
    findings = check_duplicate_segments(impl(segments=segs), ctx("SEG-006"))
    assert findings == []


# SEG-007
def test_segment_nesting_depth_fires():
    segs = [
        segment("segments/deep", nesting_depth=8),
        segment("segments/shallow", nesting_depth=2),
    ]
    findings = check_segment_nesting_depth(impl(segments=segs), ctx("SEG-007", max_depth=4))
    assert len(findings) == 1


def test_segment_nesting_depth_quiet_within_threshold():
    segs = [segment(f"segments/s_{i}", nesting_depth=3) for i in range(5)]
    findings = check_segment_nesting_depth(impl(segments=segs), ctx("SEG-007", max_depth=4))
    assert findings == []

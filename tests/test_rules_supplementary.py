"""Tests for supplementary rule checks that read --extra-input data.

These checks are registered but kept out of the default packs — they only
fire when an operator opts in by attaching the relevant key via
`--extra-input KEY=PATH`. Tests exercise them directly with synthetic
Implementation objects.
"""

from __future__ import annotations

from _rule_test_helpers import ctx, impl
from sdr_grader.rules.checks.supplementary import (
    check_launch_required_data_elements,
)


def _impl_with_launch(launch_payload):
    """Build an Implementation with a 'launch' supplementary payload attached."""
    i = impl()
    i.supplementary_data["launch"] = launch_payload
    return i


def test_launch_missing_required_elements_fires():
    i = _impl_with_launch(
        {
            "property": {"name": "Production Web"},
            "data_elements": [
                {"name": "page_name", "type": "JS Variable"},
            ],
        }
    )
    c = ctx("LAUNCH-001", required=["page_name", "user_id", "session_id"])
    findings = check_launch_required_data_elements(i, c)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "LAUNCH-001"
    assert "2 required Launch data element" in f.title
    # Body should enumerate the specific missing names.
    bodies = " ".join(b.html or " ".join(b.items or []) for b in f.body if b)
    assert "user_id" in bodies
    assert "session_id" in bodies


def test_launch_all_required_present_silent():
    i = _impl_with_launch(
        {
            "property": {"name": "Production Web"},
            "data_elements": [
                {"name": "page_name", "type": "JS Variable"},
                {"name": "user_id", "type": "JS Variable"},
            ],
        }
    )
    c = ctx("LAUNCH-001", required=["page_name", "user_id"])
    assert check_launch_required_data_elements(i, c) == []


def test_launch_no_supplementary_attached_silent():
    """Without --extra-input launch=..., the rule must stay silent rather
    than firing against an empty inventory."""
    c = ctx("LAUNCH-001", required=["page_name"])
    assert check_launch_required_data_elements(impl(), c) == []


def test_launch_empty_required_list_silent():
    """If the rubric forgets to list required elements, the rule no-ops
    instead of falsely flagging every element as missing."""
    i = _impl_with_launch({"data_elements": [{"name": "x"}]})
    c = ctx("LAUNCH-001")
    assert check_launch_required_data_elements(i, c) == []


def test_launch_payload_not_a_dict_silent():
    """Malformed launch payload (list, string, None) is treated as absent."""
    for payload in [["not", "a", "dict"], "string", 42]:
        i = _impl_with_launch(payload)
        c = ctx("LAUNCH-001", required=["x"])
        assert check_launch_required_data_elements(i, c) == []


def test_launch_data_elements_not_a_list_silent():
    """If data_elements is the wrong shape (dict, None), treat as no
    elements present rather than crashing."""
    i = _impl_with_launch({"data_elements": {"wrong": "shape"}})
    c = ctx("LAUNCH-001", required=["x"])
    assert check_launch_required_data_elements(i, c) == []


def test_launch_singular_title_when_one_missing():
    i = _impl_with_launch(
        {"data_elements": [{"name": "page_name"}]},
    )
    c = ctx("LAUNCH-001", required=["page_name", "user_id"])
    findings = check_launch_required_data_elements(i, c)
    assert len(findings) == 1
    # Singular form when exactly one missing.
    assert "1 required Launch data element missing" in findings[0].title


def test_launch_missing_elements_without_remediation_has_no_empty_block():
    """Spec F36: no FindingBlock with empty html when remediation is unset."""
    import dataclasses

    i = _impl_with_launch(
        {
            "property": {"name": "Production Web"},
            "data_elements": [{"name": "page_name", "type": "JS Variable"}],
        }
    )
    c = dataclasses.replace(
        ctx("LAUNCH-001", required=["page_name", "user_id", "session_id"]),
        remediation="",
    )
    findings = check_launch_required_data_elements(i, c)
    assert len(findings) == 1
    for block in findings[0].body:
        assert not (block.kind == "paragraph" and block.html == "")
    assert len(findings[0].body) == 2

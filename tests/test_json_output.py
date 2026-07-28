"""Machine-readable report vocabulary and compatibility tests."""

from __future__ import annotations

import pytest

from fixtures.demo_report import build_demo_report
from sdr_grader import __version__
from sdr_grader.render import Remediation
from sdr_grader.render.json_output import report_to_dict


def test_report_json_declares_schema_and_stable_evaluation_identity():
    data = report_to_dict(build_demo_report())

    assert data["schema_version"] == 1
    assert data["instance_id"] == "dv_prod_web"
    assert data["adapter"] == {
        "platform": "CJA",
        "tool": "cja_auto_sdr",
        "version": "3.5.17",
    }
    assert data["rubric"] == {"pack": "strict", "version": "2.0"}
    assert data["tool_version"] == __version__


def test_remediation_serializes_truthful_weight_and_deprecated_alias():
    remediation = report_to_dict(build_demo_report())["remediations"][0]

    assert remediation["priority_weight"] == 6
    assert remediation["impact_pts"] == remediation["priority_weight"]


def test_legacy_impact_pts_constructor_remains_readable():
    remediation = Remediation(
        text="Legacy consumer",
        refs=["LEGACY-1"],
        impact_pts=7,
    )

    assert remediation.priority_weight == 7
    assert remediation.impact_pts == 7
    remediation.impact_pts = 9
    assert remediation.priority_weight == 9


def test_conflicting_remediation_aliases_are_rejected():
    with pytest.raises(ValueError, match="must agree"):
        Remediation(
            text="Ambiguous",
            priority_weight=5,
            impact_pts=3,
        )

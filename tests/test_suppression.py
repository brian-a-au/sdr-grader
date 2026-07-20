"""Tests for suppression config and pragmatic pack."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sdr_grader.adapters.cja import adapt
from sdr_grader.cli.exit_codes import SUCCESS
from sdr_grader.cli.main import main
from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.core.grader import grade
from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.rubric import load_rubric
from sdr_grader.rules.suppression import (
    SuppressedRule,
    Suppression,
    apply_to_findings,
    apply_to_rubric,
    load_suppression,
    summarize_suppressed,
)

FIXTURES = Path(__file__).parent / "fixtures"
STRICT_PACK = (
    Path(__file__).resolve().parent.parent / "src" / "sdr_grader" / "rules" / "packs" / "strict"
)
PRAGMATIC_PACK = STRICT_PACK.parent / "pragmatic"


def _finding(rule_id: str, severity: str = "medium") -> Finding:
    return Finding(
        id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        category="schema hygiene",
        title="x",
        body=[FindingBlock(kind="paragraph", html="x")],
    )


def _write_suppression(tmp_path: Path, content: object) -> Path:
    config = tmp_path / ".sdr-grader.yaml"
    config.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return config


# ---------------------------------------------------------------------------
# Suppression loader
# ---------------------------------------------------------------------------


def test_load_suppression_returns_empty_when_file_missing(tmp_path):
    suppression = load_suppression(tmp_path / "missing.yaml")
    assert suppression == Suppression()


def test_load_suppression_parses_full_shape(tmp_path):
    config = tmp_path / ".sdr-grader.yaml"
    config.write_text(
        """
suppress:
  - rule: NAME-002
    reason: legacy IDs
  - rule: SEG-007
    components: [seg_qualified_lead_v3]
    reason: documented exception

severity_overrides:
  CALC-014: medium

category_weights:
  governance_posture: 0.30
""".lstrip()
    )
    suppression = load_suppression(config)
    assert {s.rule_id for s in suppression.suppressed} == {"NAME-002", "SEG-007"}
    assert "NAME-002" in suppression.fully_suppressed_ids
    assert "SEG-007" not in suppression.fully_suppressed_ids
    assert suppression.component_suppressions == {"SEG-007": {"seg_qualified_lead_v3"}}
    assert suppression.severity_overrides == {"CALC-014": "medium"}
    assert suppression.category_weight_overrides == {"governance_posture": 0.30}


def test_load_suppression_rejects_nonmapping_root(tmp_path):
    config = _write_suppression(tmp_path, ["not", "a", "mapping"])

    with pytest.raises(
        RubricValidationError,
        match=r"\.sdr-grader\.yaml: suppression config must be a mapping, got list",
    ):
        load_suppression(config)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ({"suppress": ["NAME-002"]}, "suppress entries must be mappings"),
        ({"suppress": [{}]}, "suppress entry missing 'rule' string"),
        (
            {"suppress": [{"rule": "NAME-002", "components": "metric_1"}]},
            "suppress\\[NAME-002\\] 'components' must be a list",
        ),
        ({"severity_overrides": ["NAME-002"]}, "severity_overrides must be a mapping"),
        (
            {"severity_overrides": {"NAME-002": "urgent"}},
            "severity_overrides\\['NAME-002'\\].*not a valid severity",
        ),
        ({"category_weights": ["schema_hygiene"]}, "category_weights override must be a mapping"),
        (
            {"category_weights": {"schema_hygiene": "heavy"}},
            "category_weights\\['schema_hygiene'\\] is not numeric",
        ),
    ],
)
def test_load_suppression_rejects_invalid_nested_shapes(tmp_path, content, message):
    config = _write_suppression(tmp_path, content)

    with pytest.raises(RubricValidationError, match=message):
        load_suppression(config)


# ---------------------------------------------------------------------------
# apply_to_findings
# ---------------------------------------------------------------------------


def test_apply_to_findings_drops_suppressed_rules():
    findings = [_finding("SCH-003"), _finding("CALC-014", severity="high")]
    suppression = Suppression(suppressed=[SuppressedRule("SCH-003", reason="quiet")])
    out = apply_to_findings(findings, suppression)
    assert [f.id for f in out] == ["CALC-014"]


def test_apply_to_findings_overrides_severity():
    findings = [_finding("CALC-014", severity="high")]
    suppression = Suppression(severity_overrides={"CALC-014": "low"})
    out = apply_to_findings(findings, suppression)
    assert out[0].severity == "low"


def test_component_suppression_is_recorded_but_does_not_drop_finding():
    finding = _finding("SEG-007")
    suppression = Suppression(
        suppressed=[SuppressedRule("SEG-007", reason="one segment", components=["seg_1"])]
    )

    assert apply_to_findings([finding], suppression) == [finding]


def test_suppression_summary_groups_reasons_and_omits_empty_rule_ids():
    suppression = Suppression(
        suppressed=[
            SuppressedRule("NAME-002", reason="legacy"),
            SuppressedRule("SCH-003", reason="legacy"),
            SuppressedRule("CALC-014", reason=""),
            SuppressedRule("", reason="ignored"),
        ]
    )

    summaries = summarize_suppressed(suppression)
    assert [(summary.reason, summary.ids) for summary in summaries] == [
        ("legacy", ["NAME-002", "SCH-003"]),
        ("(no reason recorded)", ["CALC-014"]),
    ]


# ---------------------------------------------------------------------------
# apply_to_rubric
# ---------------------------------------------------------------------------


def test_apply_to_rubric_overrides_category_weights_and_renormalizes():
    rubric = load_rubric(STRICT_PACK)
    suppression = Suppression(category_weight_overrides={"schema_hygiene": 0.50})
    new_rubric = apply_to_rubric(rubric, suppression)
    assert sum(new_rubric.category_weights.values()) == 1.0
    # The override slot should win.
    schema_share = new_rubric.category_weights["schema_hygiene"]
    assert schema_share > rubric.category_weights["schema_hygiene"]


def test_apply_to_rubric_overrides_severity_per_rule():
    rubric = load_rubric(STRICT_PACK)
    suppression = Suppression(severity_overrides={"SCH-003": "low"})
    new_rubric = apply_to_rubric(rubric, suppression)
    sch003 = next(r for r in new_rubric.rules if r.id == "SCH-003")
    assert sch003.severity == "low"


@pytest.mark.parametrize("override", [0.0, -0.25])
def test_apply_to_rubric_clamps_nonpositive_category_weight_to_zero(override):
    rubric = load_rubric(STRICT_PACK)
    suppression = Suppression(category_weight_overrides={"schema_hygiene": override})

    new_rubric = apply_to_rubric(rubric, suppression)

    assert new_rubric.category_weights["schema_hygiene"] == 0.0
    assert sum(new_rubric.category_weights.values()) == pytest.approx(1.0)


def test_apply_to_rubric_preserves_all_nonpositive_weights_without_dividing():
    rubric = load_rubric(STRICT_PACK)
    overrides = dict.fromkeys(rubric.category_weights, 0.0)

    new_rubric = apply_to_rubric(rubric, Suppression(category_weight_overrides=overrides))

    assert new_rubric.category_weights == overrides


# ---------------------------------------------------------------------------
# End-to-end: messy fixture + suppression
# ---------------------------------------------------------------------------


def test_grader_with_suppression_skips_suppressed_findings(tmp_path):
    snapshot = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    impl = adapt(snapshot, source="test")
    rubric = load_rubric(STRICT_PACK)

    baseline = grade(impl, rubric)
    sch003_in_baseline = any(f.id == "SCH-003" for f in baseline.findings)
    assert sch003_in_baseline

    suppression = Suppression(suppressed=[SuppressedRule("SCH-003", reason="working through it")])
    suppressed_report = grade(impl, rubric, suppression=suppression)
    assert all(f.id != "SCH-003" for f in suppressed_report.findings)
    # Suppression appears in methodology skipped section.
    assert any("SCH-003" in s.ids for s in suppressed_report.methodology.skipped)


def test_cli_loads_suppression_config(tmp_path):
    config = tmp_path / ".sdr-grader.yaml"
    config.write_text("""suppress:\n  - rule: SCH-003\n    reason: working through it\n""")
    output = tmp_path / "out.html"
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(output),
            "--suppress-config",
            str(config),
            "--quiet",
        ]
    )
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert "89 components lack descriptions" not in html  # SCH-003 suppressed
    assert "SCH-003" in html  # but listed as skipped


# ---------------------------------------------------------------------------
# Pragmatic pack
# ---------------------------------------------------------------------------


def test_pragmatic_pack_loads_with_same_rule_ids_as_strict():
    strict = load_rubric(STRICT_PACK)
    pragmatic = load_rubric(PRAGMATIC_PACK)
    assert {r.id for r in pragmatic.rules} == {r.id for r in strict.rules}


def test_pragmatic_pack_grades_messy_more_leniently():
    snapshot = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    impl = adapt(snapshot, source="test")
    strict_report = grade(impl, load_rubric(STRICT_PACK))
    pragmatic_report = grade(impl, load_rubric(PRAGMATIC_PACK))
    assert pragmatic_report.overall_pct > strict_report.overall_pct


def test_cli_can_use_pragmatic_pack(tmp_path):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "p.html"),
            "--pack",
            "pragmatic",
            "--quiet",
        ]
    )
    assert rc == SUCCESS

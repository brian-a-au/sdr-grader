"""Custom governance date evidence uses the shared UTC instant contract."""

import json
from pathlib import Path

import pytest
import yaml

from _rule_test_helpers import component, ctx, impl
from sdr_grader.cli.main import BUNDLED_PACKS_DIR, main
from sdr_grader.rules.checks.governance import check_doc_drift, check_snapshot_age

EQUIVALENTS = [
    "2026-01-01T00:00:00Z", "2026-01-01T00:00:00+00:00",
    "2026-01-01T00:00:00.000Z", "2025-12-31T16:00:00-08:00",
    "2026-01-01", "2026-01-01 00:00:00",
]


@pytest.mark.parametrize("timestamp", EQUIVALENTS)
@pytest.mark.parametrize("days,expected", [(90, False), (91, True)])
def test_age_equivalent_instants_keep_day_boundary(timestamp, days, expected):
    model = impl()
    model.snapshot_taken_at = timestamp
    reference = "2026-04-01T23:59:59.999Z" if days == 90 else "2026-04-02T00:00:00+00:00"
    findings = check_snapshot_age(model, ctx("GOV-002", max_age_days=90, reference_date=reference))
    assert bool(findings) is expected


@pytest.mark.parametrize("timestamp", EQUIVALENTS)
@pytest.mark.parametrize("source", ["params", "supplementary", "metadata"])
@pytest.mark.parametrize("modified,expected", [
    ("2025-12-31T23:59:59.999Z", False),
    ("2026-01-01T00:00:00+00:00", False),
    ("2026-01-01T00:00:00.001Z", True),
])
def test_doc_drift_sources_compare_instants(timestamp, source, modified, expected):
    c = component(1)
    c.modified_at = modified
    model = impl(metrics=[c])
    params = {"threshold": 0.2}
    if source == "params":
        params["last_sdr_update_at"] = timestamp
        model.supplementary_data = {"sdr": {"last_updated_at": "2030-01-01"}}
    elif source == "supplementary":
        model.supplementary_data = {"sdr": {"last_updated_at": timestamp}}
        model.raw = {"metadata": {"SDR Last Updated": "2030-01-01"}}
    else:
        model.raw = {"metadata": {"SDR Last Updated": timestamp}}
    assert bool(check_doc_drift(model, ctx("GOV-006", **params))) is expected


@pytest.mark.parametrize("timestamp", [None, "", "invalid", "2026-99-99"])
def test_unavailable_or_invalid_dates_remain_noop(timestamp):
    c = component(1)
    c.modified_at = timestamp
    model = impl(metrics=[c])
    model.snapshot_taken_at = timestamp
    assert check_snapshot_age(model, ctx("GOV-002", reference_date="2026-12-01")) == []
    assert check_doc_drift(model, ctx("GOV-006", last_sdr_update_at="2025-01-01")) == []
    c.modified_at = "2026-01-01"
    assert check_doc_drift(model, ctx("GOV-006", last_sdr_update_at=timestamp)) == []


@pytest.mark.parametrize("rule_id,check,params", [
    ("GOV-002", "snapshot_age", {"reference_date": "2026-04-25T00:00:00Z", "max_age_days": 90}),
    ("GOV-006", "doc_drift", {"last_sdr_update_at": "2025-01-01T00:00:00Z", "threshold": 0.2}),
])
def test_custom_governance_cli_equivalence_and_gate(tmp_path, rule_id, check, params):
    pack = tmp_path / "pack"
    pack.mkdir()
    meta = yaml.safe_load((BUNDLED_PACKS_DIR / "strict/_meta.yaml").read_text())
    meta["category_weights"] = {"governance_posture": 1.0}
    (pack / "_meta.yaml").write_text(yaml.safe_dump(meta))
    (pack / "governance.yaml").write_text(yaml.safe_dump({
        "category": "governance_posture", "rules": [{
            "id": rule_id, "name": rule_id, "severity": "high", "platforms": ["cja"],
            "check": check, "params": params,
        }],
    }))
    source, output, html = [tmp_path / name for name in ("input.json", "grade.json", "grade.html")]
    baseline = None
    for timestamp in EQUIVALENTS:
        source.write_text(json.dumps({
            "metadata": {"Data View ID": "dates", "Generation Timestamp": timestamp},
            "metrics": [], "dimensions": [{"id": "d", "name": "Dimension", "modified_at": timestamp}],
        }))
        args = [str(source), "--rubric", str(pack), "--output", str(html),
                "--json", str(output), "--quiet", "--fail-below", "A"]
        assert main(args) == 2
        payload = json.loads(output.read_text())
        assert payload["overall_pct"] == 0
        assert [f["id"] for f in payload["findings"]] == [rule_id]
        # GOV-002 intentionally displays the source date text in this paragraph.
        if rule_id == "GOV-002":
            paragraph = payload["findings"][0]["body"][0]
            paragraph["html"] = paragraph["html"].replace(timestamp, EQUIVALENTS[0])
        if baseline is None:
            baseline = payload
        assert payload == baseline
        before = (output.read_bytes(), html.read_bytes())
        assert main(args) == 2
        assert (output.read_bytes(), html.read_bytes()) == before
        assert rule_id in html.read_text()


def test_custom_date_checks_remain_absent_from_bundled_packs():
    for pack in ("strict", "pragmatic"):
        rules = yaml.safe_load((Path(BUNDLED_PACKS_DIR) / pack / "governance.yaml").read_text())
        assert not {"GOV-002", "GOV-006"} & {rule["id"] for rule in rules["rules"]}

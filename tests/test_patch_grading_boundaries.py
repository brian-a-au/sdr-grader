"""Audit regressions for stable CI gates and malformed input boundaries."""

import itertools
import json
from pathlib import Path

import pytest
import yaml

from sdr_grader.cli.main import main

PACK = Path(__file__).parents[1] / "src/sdr_grader/rules/packs/strict"


def _snapshot(tmp_path, **sections):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "report_suite": {"rsid": "audit"},
                "metadata": {"history_present": True, "sdr_doc_present": True},
                "metrics": [],
                "dimensions": [{"id": "variables/x", "name": "Page", "tags": ["web"]}],
                **sections,
            }
        )
    )
    return snapshot


@pytest.mark.parametrize("order", list(itertools.permutations("abc")))
@pytest.mark.parametrize("suppression_mode", ["absent", "empty", "weights"])
def test_equivalent_category_order_has_same_grade_and_exit(tmp_path, order, suppression_mode):
    # Independent arithmetic: (95*.1 + 100*.2 + 90*.7) = 92.5.
    # Existing round-to-even policy requires 92/A-minus, regardless of map order.
    pack = tmp_path / "pack"
    pack.mkdir()
    meta = yaml.safe_load((PACK / "_meta.yaml").read_text())
    weights = {"a": 0.1, "b": 0.2, "c": 0.7}
    meta["category_weights"] = {key: weights[key] for key in order}
    meta["severity_weights"] = {"critical": 19, "high": 9, "medium": 1, "low": 1}
    (pack / "_meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    for cat, severity in [("a", "critical"), ("b", "medium"), ("c", "high")]:
        rules = [
            {
                "id": cat + "-pass",
                "severity": severity,
                "platforms": ["aa"],
                "check": "missing_descriptions",
                "params": {"threshold": 1, "targets": ["dimensions"]},
            }
        ]
        if cat != "b":
            rules.append(
                {
                    "id": cat + "-fail",
                    "severity": "low",
                    "platforms": ["aa"],
                    "check": "missing_descriptions",
                    "params": {"threshold": 0, "targets": ["dimensions"]},
                }
            )
        (pack / f"{cat}.yaml").write_text(yaml.safe_dump({"category": cat, "rules": rules}))
    html, output = tmp_path / "report.html", tmp_path / "report.json"
    args = [
        str(_snapshot(tmp_path)),
        "--rubric",
        str(pack),
        "--output",
        str(html),
        "--json",
        str(output),
        "--fail-below",
        "A",
    ]
    if suppression_mode != "absent":
        config = tmp_path / "config.yaml"
        config.write_text(
            yaml.safe_dump({"category_weights": weights} if suppression_mode == "weights" else {})
        )
        args += ["--suppress-config", str(config)]
    assert main(args) == 2
    report = json.loads(output.read_text())
    assert (report["overall_pct"], report["grade"]) == (92, "A−")
    assert {c["name"]: c["pct"] for c in report["categories"]} == {"a": 95, "b": 100, "c": 90}
    assert "92" in html.read_text()


@pytest.mark.parametrize("value", [False, 0, {}, "", None, [7], [None], [False]])
def test_invalid_suppression_scope_rejected_before_output(tmp_path, value, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"suppress": [{"rule": "SCH-003", "components": value}]}))
    html, output = tmp_path / "report.html", tmp_path / "report.json"
    assert (
        main(
            [
                str(_snapshot(tmp_path)),
                "--suppress-config",
                str(config),
                "--output",
                str(html),
                "--json",
                str(output),
            ]
        )
        == 3
    )
    assert "components" in capsys.readouterr().err
    assert not html.exists() and not output.exists()


@pytest.mark.parametrize("definition", [7, 0, True, False, [1], [], "malformed", ""])
def test_malformed_aa_definition_is_contextual_cli_error(tmp_path, definition, capsys):
    snapshot = _snapshot(tmp_path, calculated_metrics=[{"id": "cm1", "definition": definition}])
    html, output = tmp_path / "report.html", tmp_path / "report.json"
    assert main([str(snapshot), "--output", str(html), "--json", str(output)]) == 1
    error = capsys.readouterr().err
    assert "calculated_metrics[0]" in error and "definition" in error
    assert "Traceback" not in error
    assert not html.exists() and not output.exists()

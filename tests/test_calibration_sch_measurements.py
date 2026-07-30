"""Pin SCH-003 calibration to the bundled rule's decision statistic."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from _rule_test_helpers import component, impl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import calibrate_thresholds as ct  # noqa: E402


def _components(
    count: int,
    missing: int,
    *,
    component_type: str,
    prefix: str,
):
    return [
        component(
            index,
            comp_type=component_type,
            cid=f"{prefix}/{index}",
            description=None if index < missing else "documented",
        )
        for index in range(count)
    ]


def test_sch_003_targets_come_from_strict_pack():
    assert ct.SCH_003_TARGETS == ("metrics", "dimensions")


def test_sch_003_uses_maximum_per_target_ratio_not_aggregate():
    implementation = impl(
        metrics=_components(10, 9, component_type="metric", prefix="metrics"),
        dimensions=_components(
            90,
            0,
            component_type="dimension",
            prefix="dimensions",
        ),
    )

    assert ct._sch_missing_desc_ratio(implementation) == (0.9, 10)


def test_sch_003_excludes_derived_fields_not_configured_by_pack():
    implementation = impl(
        metrics=_components(10, 1, component_type="metric", prefix="metrics"),
        dimensions=_components(
            20,
            4,
            component_type="dimension",
            prefix="dimensions",
        ),
        derived=_components(
            100,
            100,
            component_type="derived_field",
            prefix="derived",
        ),
    )

    assert ct._sch_missing_desc_ratio(implementation) == (0.2, 20)


def test_sch_003_empty_configured_populations_have_empty_denominator():
    implementation = impl(
        derived=_components(
            5,
            5,
            component_type="derived_field",
            prefix="derived",
        )
    )

    assert ct._sch_missing_desc_ratio(implementation) == (0.0, 0)


def test_manifest_loads_only_explicitly_admitted_human_reviewed_entries(
    tmp_path,
):
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "entries": [
                    {
                        "anon_id": "admitted",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": {
                            "admitted": True,
                            "reviewed_by": "maintainer",
                            "reviewed_at": "2026-07-29",
                        },
                    },
                    {
                        "anon_id": "compatibility-only",
                        "anonymization": {"reviewed_descriptions": False},
                        "calibration": {"admitted": False},
                    },
                    {
                        "anon_id": "missing-reviewer",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": {
                            "admitted": True,
                            "reviewed_at": "2026-07-29",
                        },
                    },
                    {
                        "anon_id": "blank-reviewer",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": {
                            "admitted": True,
                            "reviewed_by": " ",
                            "reviewed_at": "2026-07-29",
                        },
                    },
                    {
                        "anon_id": "invalid-date",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": {
                            "admitted": True,
                            "reviewed_by": "maintainer",
                            "reviewed_at": "2026-02-30",
                        },
                    },
                    {
                        "anon_id": "non-string-date",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": {
                            "admitted": True,
                            "reviewed_by": "maintainer",
                            "reviewed_at": 20260729,
                        },
                    },
                    {
                        "anon_id": "invalid-calibration-block",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": "admitted",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert [entry["anon_id"] for entry in ct._load_manifest(manifest)] == [
        "admitted"
    ]


def test_calibration_report_fails_closed_when_admitted_snapshot_is_missing(
    tmp_path,
    capsys,
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = corpus / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "entries": [
                    {
                        "anon_id": "missing-snapshot",
                        "file": "missing.json",
                        "platform": "cja",
                        "anonymization": {"reviewed_descriptions": True},
                        "calibration": {
                            "admitted": True,
                            "reviewed_by": "maintainer",
                            "reviewed_at": "2026-07-29",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "thresholds.md"

    result = ct.main(
        [
            "--corpus",
            str(corpus),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ]
    )

    assert result == 1
    assert not output.exists()
    captured = capsys.readouterr()
    assert "WARN: manifest entry missing-snapshot points to missing file" in captured.err
    assert "ERROR: could not measure 1 calibration-admitted entry" in captured.err
    assert "No report was written." in captured.err


def test_distribution_report_does_not_claim_calibration():
    report = ct._render_report({})

    assert report.startswith("# Threshold distribution evidence\n")
    assert "does not establish calibration" in report
    assert "calibration corpus" not in report

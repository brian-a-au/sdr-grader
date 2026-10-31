"""End-to-end CLI tests (Phase 3: Mode 1 only)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from sdr_grader import __version__
from sdr_grader.cli.exit_codes import (
    GRADE_BELOW_THRESHOLD,
    RUBRIC_VALIDATION_FAILURE,
    RUNTIME_ERROR,
    SUCCESS,
)
from sdr_grader.cli.main import BUNDLED_PACKS_DIR, main
from sdr_grader.core.exceptions import UnknownPlatformError

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_version_reports_installed_package_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out == f"sdr-grader {__version__}\n"


def test_cli_runs_against_messy_fixture_and_writes_html(tmp_path, capsys):
    output = tmp_path / "report.html"
    rc = main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(output)])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert "SCH-003" in html
    assert "120 components lack descriptions" in html
    assert "Production Web Analytics" in html
    err = capsys.readouterr().err
    # stderr summary mentions the grade letter and the instance.
    assert "grade " in err
    assert "dv_messy_prod_web" in err


def test_cli_default_output_filename_is_keyed_by_instance(tmp_path, monkeypatch, capsys):
    """No --output → default filename must encode the instance so batch runs
    across many instances don't collide on a single grade-{ts}.html name
    (issue #2). report.id is `SDR-{YYYY-MMDD}-{INSTANCE-TOKEN}`."""
    monkeypatch.chdir(tmp_path)
    rc = main([str(FIXTURES / "cja_snapshot_messy.json"), "--quiet"])
    assert rc == SUCCESS
    outputs = list(tmp_path.glob("grade-*.html"))
    assert len(outputs) == 1
    name = outputs[0].name
    # Filename must contain the sanitized instance token so different
    # instances graded at the same second don't write to the same path.
    assert "DV-MESSY-PROD-WEB" in name
    assert name.startswith("grade-SDR-")
    assert name.endswith(".html")


def test_cli_quiet_suppresses_stderr_summary(tmp_path, capsys):
    output = tmp_path / "report.html"
    rc = main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(output), "--quiet"])
    assert rc == SUCCESS
    err = capsys.readouterr().err
    assert err == ""


def test_cli_clean_fixture_grades_well(tmp_path):
    output = tmp_path / "clean.html"
    rc = main([str(FIXTURES / "cja_snapshot_clean.json"), "--output", str(output)])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert "Clean Production Web Analytics" in html
    # The clean fixture has no missing descriptions, so SCH-003 must not fire.
    assert "lack descriptions" not in html


def test_cli_rejects_missing_snapshot(tmp_path, capsys):
    rc = main([str(tmp_path / "does_not_exist.json"), "--output", str(tmp_path / "out.html")])
    assert rc == RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "snapshot file not found" in err


def test_cli_rejects_invalid_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    rc = main([str(bad), "--output", str(tmp_path / "out.html")])
    assert rc == RUNTIME_ERROR
    assert "not valid JSON" in capsys.readouterr().err


def test_cli_surrogate_snapshot_is_controlled_and_writes_no_artifact(tmp_path, capsys):
    snapshot = json.loads((FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8"))
    snapshot["metrics"][0]["description"] = "\ud800"
    source = tmp_path / "surrogate.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    output = tmp_path / "out.html"

    rc = main([str(source), "--output", str(output), "--quiet"])

    assert rc == RUNTIME_ERROR
    assert not output.exists()
    diagnostics = capsys.readouterr().err
    assert "surrogate" in diagnostics
    assert "Traceback" not in diagnostics
    assert not any(0xD800 <= ord(character) <= 0xDFFF for character in diagnostics)


def test_cli_adapter_error_does_not_echo_snapshot_values_or_private_path(tmp_path, capsys):
    private_dir = tmp_path / "PRIVATE-CLI-PATH"
    private_dir.mkdir()
    snapshot = private_dir / "PRIVATE-CLI-SNAPSHOT.json"
    canary = "PRIVATE-CLI-RECORD-CANARY"
    snapshot.write_text(
        json.dumps(
            {
                "report_suite": {"rsid": "rs1"},
                "dimensions": [{"name": canary, "secret": "\x1bPRIVATE"}],
                "metrics": [],
            }
        ),
        encoding="utf-8",
    )

    rc = main([str(snapshot), "--platform", "aa", "--quiet"])

    assert rc == RUNTIME_ERROR
    diagnostics = capsys.readouterr().err
    assert "AA dimensions[0]" in diagnostics
    assert canary not in diagnostics
    assert "PRIVATE-CLI-PATH" not in diagnostics
    assert "\x1b" not in diagnostics
    assert "Traceback" not in diagnostics


def test_cli_rejects_unknown_pack(tmp_path, capsys):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--pack",
            "no_such_pack",
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "not found" in capsys.readouterr().err


def test_cli_rejects_invalid_rubric_dir(tmp_path, capsys):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--rubric",
            str(tmp_path / "no_such_dir"),
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "rubric directory not found" in capsys.readouterr().err


def test_cli_rejects_cja_snapshot_with_aa_override(tmp_path, capsys):
    """A CJA snapshot routed through the AA adapter must fail validation."""
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--platform",
            "aa",
        ]
    )
    assert rc == RUNTIME_ERROR
    assert "report_suite" in capsys.readouterr().err


def test_cli_fail_below_returns_grade_below_threshold(tmp_path):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--quiet",
            "--fail-below",
            "B-",
        ]
    )
    assert rc == GRADE_BELOW_THRESHOLD


def test_cli_fail_below_passes_when_grade_meets_threshold(tmp_path):
    # Clean fixture grades C; D is below it, so the threshold is met.
    # External-context rules (GOV-001/003) fire even on the clean fixture
    # because the loader can't prove history / SDR presence yet.
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--quiet",
            "--fail-below",
            "D",
        ]
    )
    assert rc == SUCCESS


def test_cli_aa_grade_is_consistent_across_file_stdin_and_json(
    tmp_path,
    monkeypatch,
):
    import io
    import sys

    snapshot_path = FIXTURES / "aa_snapshot_messy.json"
    file_html = tmp_path / "file.html"
    file_json = tmp_path / "file.json"
    file_rc = main(
        [
            str(snapshot_path),
            "--output",
            str(file_html),
            "--json",
            str(file_json),
            "--quiet",
            "--fail-below",
            "F",
        ]
    )

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(snapshot_path.read_text(encoding="utf-8")),
    )
    stdin_html = tmp_path / "stdin.html"
    stdin_json = tmp_path / "stdin.json"
    stdin_rc = main(
        [
            "-",
            "--output",
            str(stdin_html),
            "--json",
            str(stdin_json),
            "--quiet",
            "--fail-below",
            "D",
        ]
    )

    assert file_rc == SUCCESS
    assert stdin_rc == GRADE_BELOW_THRESHOLD
    assert json.loads(file_json.read_text(encoding="utf-8"))["overall_pct"] == 55
    assert json.loads(file_json.read_text(encoding="utf-8"))["grade"] == "F"
    assert file_json.read_bytes() == stdin_json.read_bytes()
    assert file_html.read_bytes() == stdin_html.read_bytes()


def test_cli_invalid_rubric_yaml_returns_validation_failure(tmp_path, capsys):
    pack = tmp_path / "broken_pack"
    pack.mkdir()
    (pack / "_meta.yaml").write_text("pack: test\n")  # missing required keys
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--rubric",
            str(pack),
        ]
    )
    assert rc == RUBRIC_VALIDATION_FAILURE
    assert "rubric error" in capsys.readouterr().err


def test_cli_malformed_rubric_yaml_is_exit_3_with_no_artifact(
    tmp_path,
    capsys,
):
    pack = tmp_path / "broken_pack"
    pack.mkdir()
    (pack / "_meta.yaml").write_text(
        "category_weights: [unterminated\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(output),
            "--rubric",
            str(pack),
        ]
    )

    assert rc == RUBRIC_VALIDATION_FAILURE
    assert not output.exists()
    diagnostics = capsys.readouterr().err
    assert "rubric error:" in diagnostics
    assert "Traceback" not in diagnostics


def test_cli_invalid_numeric_rubric_is_exit_3_with_no_artifact(
    tmp_path,
    capsys,
):
    source_pack = (
        Path(__file__).resolve().parent.parent / "src" / "sdr_grader" / "rules" / "packs" / "strict"
    )
    pack = tmp_path / "invalid_numeric_pack"
    shutil.copytree(source_pack, pack)
    meta_path = pack / "_meta.yaml"
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    meta["category_weights"]["schema_hygiene"] = True
    meta_path.write_text(
        yaml.safe_dump(meta, sort_keys=False),
        encoding="utf-8",
    )
    output = tmp_path / "out.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(output),
            "--rubric",
            str(pack),
        ]
    )

    assert rc == RUBRIC_VALIDATION_FAILURE
    assert not output.exists()
    diagnostics = capsys.readouterr().err
    assert "category_weights" in diagnostics
    assert "Traceback" not in diagnostics


def test_cli_missing_explicit_suppression_config_is_runtime_error(tmp_path, capsys):
    config = tmp_path / "missing-suppression.yaml"
    output = tmp_path / "out.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(output),
            "--suppress-config",
            str(config),
        ]
    )

    assert rc == RUNTIME_ERROR
    assert not output.exists()
    assert f"suppression config not found: {config}" in capsys.readouterr().err


def test_cli_invalid_existing_suppression_config_is_rubric_failure(tmp_path, capsys):
    config = tmp_path / "invalid-suppression.yaml"
    config.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    output = tmp_path / "out.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(output),
            "--suppress-config",
            str(config),
        ]
    )

    assert rc == RUBRIC_VALIDATION_FAILURE
    assert not output.exists()
    err = capsys.readouterr().err
    assert "rubric error" in err
    assert str(config) in err
    assert "must be a mapping" in err


def test_cli_json_output_writes_machine_readable_report(tmp_path):
    import json

    output = tmp_path / "out.html"
    json_path = tmp_path / "out.json"
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--output",
            str(output),
            "--json",
            str(json_path),
            "--quiet",
        ]
    )
    assert rc == SUCCESS
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["grade"]
    assert isinstance(data["overall_pct"], int)
    assert isinstance(data["findings"], list)
    assert {"name", "pct", "grade"} <= set(data["categories"][0].keys())
    assert data["generated_at"].endswith("Z")


def test_cli_html_write_failure_returns_runtime_error(tmp_path, capsys):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(tmp_path),
            "--quiet",
        ]
    )

    assert rc == RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "could not publish report outputs" in err
    assert str(tmp_path) not in err


def test_cli_json_write_failure_returns_runtime_error(tmp_path, capsys):
    output = tmp_path / "out.html"
    output.write_text("existing report", encoding="utf-8")

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(output),
            "--json",
            str(tmp_path),
            "--quiet",
        ]
    )

    assert rc == RUNTIME_ERROR
    assert output.read_text(encoding="utf-8") == "existing report"
    assert "could not publish report outputs" in capsys.readouterr().err


def test_cli_rejects_output_colliding_with_snapshot(tmp_path, capsys):
    snapshot = tmp_path / "snapshot.json"
    original = (FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8")
    snapshot.write_text(original, encoding="utf-8")

    rc = main([str(snapshot), "--output", str(snapshot)])

    assert rc == RUNTIME_ERROR
    assert snapshot.read_text(encoding="utf-8") == original
    err = capsys.readouterr().err
    assert "collides with an input path" in err
    assert "Wrote " not in err


def _snapshot_directory(tmp_path: Path) -> tuple[Path, Path, str]:
    directory = tmp_path / "snapshots"
    directory.mkdir()
    original = (FIXTURES / "cja_snapshot_clean.json").read_text(encoding="utf-8")
    (directory / "snapshot_2026-04-01.json").write_text(original, encoding="utf-8")
    latest = directory / "snapshot_2026-04-03.json"
    latest.write_text(original, encoding="utf-8")
    return directory, latest, original


@pytest.mark.parametrize("trend", [False, True])
def test_cli_rejects_output_colliding_with_snapshot_in_directory(tmp_path, capsys, trend):
    directory, latest, original = _snapshot_directory(tmp_path)

    rc = main([str(directory), *(["--trend"] if trend else []), "--output", str(latest)])

    assert rc == RUNTIME_ERROR
    assert latest.read_text(encoding="utf-8") == original
    err = capsys.readouterr().err
    assert "collides with an input path" in err
    assert "Wrote " not in err


def test_cli_rejects_output_colliding_with_rubric_file(tmp_path, capsys):
    pack = tmp_path / "pack"
    shutil.copytree(BUNDLED_PACKS_DIR / "strict", pack)
    meta = pack / "_meta.yaml"
    original = meta.read_text(encoding="utf-8")

    rc = main(
        [str(FIXTURES / "cja_snapshot_clean.json"), "--rubric", str(pack), "--output", str(meta)]
    )

    assert rc == RUNTIME_ERROR
    assert meta.read_text(encoding="utf-8") == original
    assert "collides with an input path" in capsys.readouterr().err


def test_cli_rejects_html_json_destination_alias(tmp_path, capsys):
    destination = tmp_path / "report.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(destination),
            "--json",
            str(tmp_path / "." / "report.html"),
        ]
    )

    assert rc == RUNTIME_ERROR
    assert not destination.exists()
    err = capsys.readouterr().err
    assert "resolve to the same file" in err
    assert "Wrote " not in err


def test_cli_rejects_symlink_output_before_write(tmp_path, capsys):
    target = tmp_path / "existing.html"
    target.write_text("existing report", encoding="utf-8")
    output = tmp_path / "report.html"
    output.symlink_to(target)

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(output),
        ]
    )

    assert rc == RUNTIME_ERROR
    assert target.read_text(encoding="utf-8") == "existing report"
    diagnostics = capsys.readouterr().err
    assert "symlink" in diagnostics
    assert "Wrote " not in diagnostics


def test_cli_render_failure_preserves_existing_output_set(tmp_path, monkeypatch, capsys):
    html = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    html.write_text("old html", encoding="utf-8")
    json_path.write_text("old json", encoding="utf-8")

    def fail_render(_report, *, color_pack="default"):
        raise RuntimeError("injected render failure")

    monkeypatch.setattr("sdr_grader.cli.main.render", fail_render)

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(html),
            "--json",
            str(json_path),
        ]
    )

    assert rc == RUNTIME_ERROR
    assert html.read_text(encoding="utf-8") == "old html"
    assert json_path.read_text(encoding="utf-8") == "old json"
    err = capsys.readouterr().err
    assert "could not prepare report outputs" in err
    assert "Wrote " not in err


@pytest.mark.parametrize("code", ("default", "ADBE", "OMTR", "BLUE"))
def test_cli_color_pack_applies_to_standard_report(tmp_path, code):
    output = tmp_path / f"report-{code}.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(output),
            "--color-pack",
            code,
            "--quiet",
        ]
    )

    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert f'data-color-pack="{code}"' in html
    assert f"Color pack: {code}" in html


@pytest.mark.parametrize("code", ("default", "ADBE", "OMTR", "BLUE"))
def test_cli_color_pack_applies_to_trend_report(tmp_path, code):
    snapshots = _make_trend_dir(tmp_path)
    output = tmp_path / f"trend-{code}.html"

    rc = main(
        [
            str(snapshots),
            "--trend",
            "--output",
            str(output),
            "--color-pack",
            code,
            "--quiet",
        ]
    )

    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert f'data-color-pack="{code}"' in html
    assert f"Color pack: {code}" in html


def test_cli_invalid_color_pack_preserves_existing_outputs(tmp_path, capsys):
    html = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    html.write_text("old html", encoding="utf-8")
    json_path.write_text("old json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(
            [
                str(FIXTURES / "cja_snapshot_clean.json"),
                "--output",
                str(html),
                "--json",
                str(json_path),
                "--color-pack",
                "adbe",
            ]
        )

    assert exc.value.code == 2
    assert html.read_text(encoding="utf-8") == "old html"
    assert json_path.read_text(encoding="utf-8") == "old json"
    diagnostics = capsys.readouterr().err
    for code in ("default", "ADBE", "OMTR", "BLUE"):
        assert code in diagnostics


def test_cli_color_pack_is_distinct_from_rubric_pack(tmp_path):
    output = tmp_path / "report.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--pack",
            "strict",
            "--color-pack",
            "BLUE",
            "--output",
            str(output),
            "--quiet",
        ]
    )

    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    assert 'Rubric: <span class="mono">strict@' in html
    assert "Color pack: BLUE" in html


def test_cli_color_pack_keeps_json_byte_identical_including_svg(tmp_path):
    json_outputs = []
    html_outputs = []
    for code in ("default", "BLUE"):
        html = tmp_path / f"report-{code}.html"
        json_path = tmp_path / f"report-{code}.json"
        rc = main(
            [
                str(FIXTURES / "cja_snapshot_clean.json"),
                "--distribution-data",
                "bundled",
                "--color-pack",
                code,
                "--output",
                str(html),
                "--json",
                str(json_path),
                "--quiet",
            ]
        )
        assert rc == SUCCESS
        html_outputs.append(html.read_bytes())
        json_outputs.append(json_path.read_bytes())

    assert html_outputs[0] != html_outputs[1]
    assert json_outputs[0] == json_outputs[1]
    assert b'"svg": "<svg' in json_outputs[0]


def test_cli_json_serialization_failure_preserves_existing_output_set(
    tmp_path,
    monkeypatch,
    capsys,
):
    html = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    html.write_text("old html", encoding="utf-8")
    json_path.write_text("old json", encoding="utf-8")
    monkeypatch.setattr(
        "sdr_grader.render.json_output.report_to_dict",
        lambda _report: {"unserializable": object()},
    )

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(html),
            "--json",
            str(json_path),
        ]
    )

    assert rc == RUNTIME_ERROR
    assert html.read_text(encoding="utf-8") == "old html"
    assert json_path.read_text(encoding="utf-8") == "old json"
    err = capsys.readouterr().err
    assert "could not prepare report outputs" in err
    assert "Wrote " not in err


def test_cli_run_is_deterministic(tmp_path):
    """Running twice on the same input must produce byte-identical output."""
    out_a = tmp_path / "a.html"
    out_b = tmp_path / "b.html"
    main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(out_a), "--quiet"])
    main([str(FIXTURES / "cja_snapshot_messy.json"), "--output", str(out_b), "--quiet"])
    assert out_a.read_bytes() == out_b.read_bytes()


@pytest.fixture
def _changed_snapshot_path(tmp_path):
    """Copy of the messy snapshot with one description filled in."""
    src = json.loads((FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"))
    # The dimension target exceeds SCH-003's threshold; document one item.
    src["dimensions"][0]["description"] = "Documented by test."
    out = tmp_path / "modified.json"
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def test_cli_finding_count_drops_when_descriptions_filled_in(tmp_path, _changed_snapshot_path):
    output = tmp_path / "report.html"
    rc = main([str(_changed_snapshot_path), "--output", str(output), "--quiet"])
    assert rc == SUCCESS
    html = output.read_text(encoding="utf-8")
    # The finding count is 119 now (one fewer); rule still fires.
    assert "119 components lack descriptions" in html


def _make_trend_dir(tmp_path: Path) -> Path:
    """Two dated copies of the messy fixture = a minimal trend directory."""
    src = (FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8")
    d = tmp_path / "snaps"
    d.mkdir()
    (d / "snapshot_2026-01-01.json").write_text(src, encoding="utf-8")
    (d / "snapshot_2026-02-01.json").write_text(src, encoding="utf-8")
    return d


def _write_directory_snapshot(
    directory: Path,
    name: str,
    *,
    platform: str = "cja",
    instance_id: str | None = None,
) -> Path:
    snapshot = json.loads(
        (FIXTURES / f"{platform}_snapshot_messy.json").read_text(encoding="utf-8")
    )
    if platform == "cja":
        snapshot["metadata"]["Data View ID"] = instance_id or "shared-instance"
        snapshot["metadata"].pop("history_present", None)
    else:
        snapshot["report_suite"]["rsid"] = instance_id or "shared-instance"
    path = directory / name
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


def test_directory_same_instance_sibling_supplies_history_evidence(tmp_path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_directory_snapshot(snapshots, "snapshot_2026-01-01.json")
    _write_directory_snapshot(snapshots, "snapshot_2026-02-01.json")
    output = tmp_path / "report.html"

    assert main([str(snapshots), "--output", str(output), "--quiet"]) == SUCCESS
    assert "No snapshot history detected" not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("sibling_kind", ["unrelated", "mixed", "malformed", "duplicate", "none"])
def test_directory_nonmatching_sibling_does_not_supply_history(
    tmp_path,
    sibling_kind,
):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_directory_snapshot(
        snapshots,
        "snapshot_2026-02-01.json",
        instance_id="selected-instance",
    )
    if sibling_kind == "unrelated":
        _write_directory_snapshot(
            snapshots,
            "snapshot_2026-01-01.json",
            instance_id="other-instance",
        )
    elif sibling_kind == "mixed":
        _write_directory_snapshot(
            snapshots,
            "snapshot_2026-01-01.json",
            platform="aa",
            instance_id="selected-instance",
        )
    elif sibling_kind == "malformed":
        (snapshots / "snapshot_2026-01-01.json").write_text("{", encoding="utf-8")
    elif sibling_kind == "duplicate":
        sibling = _write_directory_snapshot(
            snapshots,
            "snapshot_2026-01-01.json",
            instance_id="selected-instance",
        )
        payload = sibling.read_text().rstrip()
        sibling.write_text(payload[:-1] + ', "duplicate": 1, "duplicate": 2}')
    output = tmp_path / "report.html"

    assert main([str(snapshots), "--output", str(output), "--quiet"]) == SUCCESS
    assert "No snapshot history detected" in output.read_text(encoding="utf-8")


def test_directory_history_ignores_unknown_internal_platform_override(tmp_path):
    from sdr_grader.adapters.cja import adapt
    from sdr_grader.input.history import matching_snapshot_sibling_exists

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    selected_path = _write_directory_snapshot(
        snapshots,
        "snapshot_2026-02-01.json",
        instance_id="selected-instance",
    )
    _write_directory_snapshot(
        snapshots,
        "snapshot_2026-01-01.json",
        instance_id="selected-instance",
    )
    selected = adapt(json.loads(selected_path.read_text(encoding="utf-8")))

    assert not matching_snapshot_sibling_exists(
        snapshots,
        selected_source=selected_path,
        selected=selected,
        platform_override="unsupported",
    )


def test_trend_fail_below_gates_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _make_trend_dir(tmp_path)
    rc = main([str(d), "--trend", "--quiet", "--fail-below", "A"])
    assert rc == GRADE_BELOW_THRESHOLD


def test_trend_rejects_flags_it_cannot_honor(tmp_path, capsys):
    d = _make_trend_dir(tmp_path)
    rc = main([str(d), "--trend", "--json", str(tmp_path / "out.json")])
    assert rc == RUNTIME_ERROR
    assert "--json" in capsys.readouterr().err


def test_trend_unknown_platform_is_controlled_runtime_error(
    tmp_path,
    capsys,
):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    (snapshots / "snapshot_2026-01-01.json").write_text(
        '{"unknown": "shape"}',
        encoding="utf-8",
    )
    output = tmp_path / "trend.html"

    rc = main(
        [
            str(snapshots),
            "--trend",
            "--output",
            str(output),
        ]
    )

    assert rc == RUNTIME_ERROR
    assert not output.exists()
    diagnostics = capsys.readouterr().err
    assert "could not auto-detect platform" in diagnostics
    assert "Traceback" not in diagnostics


@pytest.mark.parametrize(
    ("platform", "version"),
    [
        ("cja", "99.0.0"),
        ("cja", "3.13.7"),
        ("aa", "99.0.0"),
        ("aa", "1.24.6"),
    ],
)
def test_cli_warns_once_for_newer_generator_without_snapshot_data(
    tmp_path,
    capsys,
    platform,
    version,
):
    snapshot = json.loads(
        (FIXTURES / f"{platform}_snapshot_messy.json").read_text(encoding="utf-8")
    )
    canary = "PRIVATE-GENERATOR-WARNING-CANARY"
    if platform == "cja":
        snapshot["metadata"]["Tool Version"] = version
        snapshot["metadata"]["private_canary"] = canary
    else:
        snapshot["tool_version"] = version
        snapshot["private_canary"] = canary
    source = tmp_path / f"{platform}.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")

    rc = main(
        [
            str(source),
            "--output",
            str(tmp_path / f"{platform}.html"),
            "--quiet",
        ]
    )

    assert rc == SUCCESS
    diagnostics = capsys.readouterr().err
    assert diagnostics.count("warning [generator-version]:") == 1
    assert f"snapshot generator version {version}" in diagnostics
    assert canary not in diagnostics


@pytest.mark.parametrize(
    ("platform", "version"),
    [
        ("cja", "3.13.6"),
        ("cja", "3.13.2"),
        ("cja", "3.11.7"),
        ("cja", "3.5.17"),
        ("cja", "unparseable"),
        ("aa", "1.24.5"),
        ("aa", "1.24.1"),
        ("aa", "1.21.10"),
        ("aa", "1.18.0"),
        ("aa", "unparseable"),
    ],
)
def test_cli_current_older_and_unparseable_generators_are_quiet(
    tmp_path,
    capsys,
    platform,
    version,
):
    snapshot = json.loads(
        (FIXTURES / f"{platform}_snapshot_messy.json").read_text(encoding="utf-8")
    )
    if platform == "cja":
        snapshot["metadata"]["Tool Version"] = version
    else:
        snapshot["tool_version"] = version
    source = tmp_path / f"{platform}-{version}.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")

    rc = main(
        [
            str(source),
            "--output",
            str(tmp_path / f"{platform}-{version}.html"),
            "--quiet",
        ]
    )

    assert rc == SUCCESS
    assert "generator-version" not in capsys.readouterr().err


def test_trend_requires_snapshot_directory_argument(capsys):
    rc = main(["--trend"])

    assert rc == RUNTIME_ERROR
    assert "--trend requires a snapshot directory path" in capsys.readouterr().err


def test_trend_rejects_directory_with_only_undated_snapshots(tmp_path, capsys):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    (snapshots / "latest.json").write_text(
        (FIXTURES / "cja_snapshot_messy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rc = main([str(snapshots), "--trend", "--output", str(tmp_path / "trend.html")])

    assert rc == RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "no snapshots" in err
    assert "parseable filename timestamps" in err


def test_trend_output_write_failure_returns_runtime_error(tmp_path, capsys):
    snapshots = _make_trend_dir(tmp_path)

    rc = main([str(snapshots), "--trend", "--output", str(tmp_path)])

    assert rc == RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "could not publish trend output" in err
    assert str(tmp_path) not in err


def test_trend_success_reports_written_summary(tmp_path, capsys):
    snapshots = _make_trend_dir(tmp_path)
    output = tmp_path / "trend.html"

    rc = main([str(snapshots), "--trend", "--output", str(output)])

    assert rc == SUCCESS
    err = capsys.readouterr().err
    assert f"Wrote {output}: trend over 2 snapshots" in err
    assert "dv_messy_prod_web" in err


def test_cli_unknown_fail_below_grade_is_runtime_error(tmp_path, capsys):
    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(tmp_path / "out.html"),
            "--fail-below",
            "platinum",
        ]
    )

    assert rc == RUNTIME_ERROR
    assert "'platinum' not found in rubric grade scale" in capsys.readouterr().err


def test_adapter_dispatch_rejects_unrecognized_detected_platform(monkeypatch):
    from sdr_grader.cli.main import _adapt_snapshot

    monkeypatch.setattr(
        "sdr_grader.input.detect.detect_platform",
        lambda _snapshot: "future-platform",
    )

    with pytest.raises(UnknownPlatformError, match="future-platform"):
        _adapt_snapshot({}, source="test", platform_override=None)


def test_cli_html_caps_component_lists_but_json_keeps_full_list(tmp_path):
    """Issue #5: a rule matching many components must not put an unbounded
    list into the HTML; the --json artifact keeps the full list."""
    dimensions = []
    for i in range(60):  # 60 duplicate-name pairs -> SCH-001 fires with 60 items
        for side in ("a", "b"):
            dimensions.append(
                {
                    "id": f"dim_{side}_{i:03d}",
                    "name": f"Duplicate Name {i:03d}",
                    "description": "documented",
                }
            )
    snapshot = {
        "metadata": {"Data View ID": "dv_cap_test", "Data View Name": "Cap Test"},
        "metrics": [],
        "dimensions": dimensions,
    }
    snapshot_path = tmp_path / "cap_test.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    output = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    rc = main(
        [
            str(snapshot_path),
            "--platform",
            "cja",
            "--output",
            str(output),
            "--json",
            str(json_path),
            "--quiet",
        ]
    )
    assert rc == SUCCESS

    html = output.read_text(encoding="utf-8")
    assert "Affected components (50)" in html
    assert "… and 10 more (see JSON output)" in html

    data = json.loads(json_path.read_text(encoding="utf-8"))
    item_counts = [
        len(block["items"])
        for finding in data["findings"]
        for block in finding["body"]
        if block["kind"] == "components" and block["items"]
    ]
    assert max(item_counts) == 60  # JSON list is complete, not capped


@pytest.mark.parametrize("route", ["file", "stdin", "extra"])
@pytest.mark.parametrize(
    "raw",
    [b"\xffPRIVATE", b'{"PRIVATE":' + b"9" * 5000 + b"}", b"[" * 10000 + b"0" + b"]" * 10000],
    ids=["utf8", "integer", "depth"],
)
def test_malformed_consumed_json_is_controlled(tmp_path, monkeypatch, capsys, route, raw):
    import io

    source = tmp_path / "bad.json"
    source.write_bytes(raw)
    output = tmp_path / "report.html"
    output.write_text("previous report")
    json_output = tmp_path / "report.json"
    json_output.write_text("previous JSON")
    args = [str(source)]
    if route == "stdin":
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))
        args = ["-"]
    elif route == "extra":
        args = [str(FIXTURES / "cja_snapshot_messy.json"), "--extra-input", f"usage={source}"]
    assert main([*args, "--output", str(output), "--json", str(json_output)]) == RUNTIME_ERROR
    assert output.read_text() == "previous report"
    assert json_output.read_text() == "previous JSON"
    err = capsys.readouterr().err
    assert "PRIVATE" not in err
    assert "Traceback" not in err


@pytest.mark.parametrize("route", ["file", "stdin", "extra", "trend"])
@pytest.mark.parametrize("existing", [False, True])
def test_duplicate_json_preserves_output_set(tmp_path, monkeypatch, capsys, route, existing):
    import io

    key = json.dumps("PRIVATE\x1b\x07" + "x" * 10000)
    snapshot = (FIXTURES / "cja_snapshot_clean.json").read_text().rstrip()
    payload = snapshot[:-1] + ', "duplicate_evidence": {' + key + ": 1, " + key + ": 2}}"
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    source = snapshots / "snapshot_2026-04-25.json"
    source.write_text(payload)
    output = tmp_path / "report.html"
    json_output = tmp_path / "report.json"
    if existing:
        output.write_text("previous report")
        json_output.write_text("previous JSON")
    args = [str(source)]
    if route == "stdin":
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        args = ["-"]
    elif route == "extra":
        args = [str(FIXTURES / "cja_snapshot_messy.json"), "--extra-input", f"usage={source}"]
    elif route == "trend":
        args = [str(snapshots), "--trend"]
    args += ["--output", str(output)]
    if route != "trend":
        args += ["--json", str(json_output)]
    assert main(args) == RUNTIME_ERROR
    if existing:
        assert output.read_text() == "previous report"
        assert json_output.read_text() == "previous JSON"
    else:
        assert not output.exists()
        assert not json_output.exists()
    err = capsys.readouterr().err
    assert "duplicate object keys" in err
    assert "PRIVATE" not in err
    assert "\x1b" not in err
    assert "\x07" not in err
    assert "Traceback" not in err
    assert len(err) < 200


def test_extra_input_over_depth_is_controlled_on_every_interpreter(tmp_path, capsys):
    source = tmp_path / "deep.json"
    source.write_text("[" * 150 + "0" + "]" * 150)
    output = tmp_path / "report.html"
    output.write_text("previous report")
    json_output = tmp_path / "report.json"
    json_output.write_text("previous JSON")
    args = [str(FIXTURES / "cja_snapshot_messy.json"), "--extra-input", f"usage={source}"]
    assert main([*args, "--output", str(output), "--json", str(json_output)]) == RUNTIME_ERROR
    assert output.read_text() == "previous report"
    assert json_output.read_text() == "previous JSON"
    err = capsys.readouterr().err
    assert "error:" in err
    assert "--extra-input usage exceeds the maximum structure depth of 100" in err
    assert "Traceback" not in err


def test_extra_input_at_max_depth_is_accepted(tmp_path):
    source = tmp_path / "deep.json"
    source.write_text("[" * 100 + "0" + "]" * 100)
    output = tmp_path / "report.html"
    args = [str(FIXTURES / "cja_snapshot_messy.json"), "--extra-input", f"usage={source}"]
    assert main([*args, "--output", str(output), "--quiet"]) == SUCCESS


@pytest.mark.parametrize("alias", ["attribution", "attribution_model"])
@pytest.mark.parametrize("value", [{"PRIVATE": "last-touch"}, ["PRIVATE"], {}, []])
def test_aa_structured_attribution_is_controlled(tmp_path, capsys, alias, value):
    snapshot = json.loads((FIXTURES / "aa_snapshot_messy.json").read_text())
    metric = snapshot["calculated_metrics"][0]
    metric.pop("attribution", None)
    metric.pop("attribution_model", None)
    metric[alias] = value
    source = tmp_path / "aa.json"
    source.write_text(json.dumps(snapshot))
    output = tmp_path / "report.html"
    output.write_text("previous report")
    assert main([str(source), "--output", str(output)]) == RUNTIME_ERROR
    assert output.read_text() == "previous report"
    assert "PRIVATE" not in capsys.readouterr().err


@pytest.mark.parametrize("target", ["suppression", "meta", "category"])
@pytest.mark.parametrize(
    "defect",
    [
        "utf8",
        "date",
        "integer",
        "digit_limit",
        "syntax",
        "tag",
        "key",
        "severity_list",
        "severity_mapping",
        "weight_positive",
        "weight_negative",
        "grade_positive",
        "grade_negative",
    ],
)
def test_yaml_validation_api_and_process_preserve_outputs(tmp_path, target, defect):
    import os
    import subprocess
    import sys

    from sdr_grader.core.exceptions import RubricValidationError
    from sdr_grader.rules.rubric import load_rubric
    from sdr_grader.rules.suppression import load_suppression

    if defect.startswith("severity") and target == "meta":
        pytest.skip("severity values belong to rules or suppression")
    if defect.startswith("weight") and target == "category":
        pytest.skip("category weights belong to metadata or suppression")
    if defect.startswith("grade") and target != "meta":
        pytest.skip("grade minima belong to metadata")
    root = Path(__file__).resolve().parent.parent
    pack = tmp_path / "pack"
    shutil.copytree(root / "src/sdr_grader/rules/packs/strict", pack)
    config = tmp_path / "suppression.yaml"
    config.write_text("{}", encoding="utf-8")
    path = (
        config
        if target == "suppression"
        else pack / ("_meta.yaml" if target == "meta" else "naming.yaml")
    )
    payloads = {
        "utf8": b"\xff",
        "date": b"unused: 2026-99-99\n",
        "integer": b"unused: !!int nope\n",
        "syntax": b"unused: [unterminated\n",
        "tag": b"unused: !unknown value\n",
        "key": b"? [a, b]\n: value\n",
    }
    field = path.name
    forbidden = None
    if defect == "digit_limit":
        limit = sys.get_int_max_str_digits()
        if not limit:
            pytest.skip("interpreter integer conversion limit disabled")
        forbidden = "9" * (limit + 1)
        path.write_text("unused: " + forbidden + "\n", encoding="utf-8")
    elif defect in payloads:
        path.write_bytes(payloads[defect])
    else:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
        if defect.startswith("severity"):
            severity = ["high"] if defect.endswith("list") else {"level": "high"}
            if target == "suppression":
                content["severity_overrides"] = {"NAME-002": severity}
            else:
                content["rules"][0]["severity"] = severity
            field = "severity"
        else:
            value = 10**400 * (-1 if defect.endswith("negative") else 1)
            forbidden = str(value)
            if defect.startswith("grade"):
                content["grade_scale"][0]["min"] = value
                field = "grade_scale"
            else:
                content.setdefault("category_weights", {})["schema_hygiene"] = value
                field = "category_weights"
        path.write_text(yaml.safe_dump(content), encoding="utf-8")
    with pytest.raises(RubricValidationError, match=field) as error:
        load_suppression(config) if target == "suppression" else load_rubric(pack)
    assert len(str(error.value)) < 500
    if defect == "utf8":
        assert "UTF-8" in str(error.value)
    if forbidden:
        assert forbidden not in str(error.value)
    html, report = tmp_path / "out.html", tmp_path / "out.json"
    command = [
        sys.executable,
        "-m",
        "sdr_grader",
        str(FIXTURES.resolve() / "cja_snapshot_messy.json"),
        "--rubric",
        str(pack),
        "--suppress-config",
        str(config),
        "--output",
        str(html),
        "--json",
        str(report),
        "--quiet",
    ]
    for existing in (True, False):
        if existing:
            html.write_bytes(b"old HTML\x00")
            report.write_bytes(b"old JSON\x00")
        result = subprocess.run(
            command,
            cwd=tmp_path,
            env=dict(os.environ, PYTHONPATH=str(root / "src")),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == RUBRIC_VALIDATION_FAILURE, result.stderr
        assert "Traceback" not in result.stderr
        assert field in result.stderr
        assert len(result.stderr) < 500
        if forbidden:
            assert forbidden not in result.stderr
        if existing:
            assert html.read_bytes() == b"old HTML\x00"
            assert report.read_bytes() == b"old JSON\x00"
            html.unlink()
            report.unlink()
        else:
            assert not html.exists()
            assert not report.exists()


def _copy_strict(tmp_path):
    pack = tmp_path / "pack"
    strict = Path(__file__).resolve().parent.parent / "src/sdr_grader/rules/packs/strict"
    shutil.copytree(strict, pack)
    return pack


def test_cli_unknown_rule_param_is_exit_3_with_no_report(tmp_path, capsys):
    pack = _copy_strict(tmp_path)
    naming = pack / "naming.yaml"
    text = naming.read_text(encoding="utf-8")
    assert "min_consistency:" in text
    naming.write_text(text.replace("min_consistency:", "min_consistancy:", 1), encoding="utf-8")
    output = tmp_path / "out.html"
    json_path = tmp_path / "out.json"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_messy.json"),
            "--rubric",
            str(pack),
            "--output",
            str(output),
            "--json",
            str(json_path),
        ]
    )

    assert rc == RUBRIC_VALIDATION_FAILURE
    assert not output.exists()
    assert not json_path.exists()
    assert "did you mean 'min_consistency'" in capsys.readouterr().err


def test_cli_unknown_project_config_section_is_exit_3(tmp_path, capsys):
    config = tmp_path / "cfg.yaml"
    config.write_text("supress:\n  - rule: NAME-002\n", encoding="utf-8")
    output = tmp_path / "out.html"

    rc = main(
        [
            str(FIXTURES / "cja_snapshot_clean.json"),
            "--output",
            str(output),
            "--suppress-config",
            str(config),
        ]
    )

    assert rc == RUBRIC_VALIDATION_FAILURE
    assert not output.exists()
    assert "unknown key 'supress'" in capsys.readouterr().err


def test_x_extension_keys_do_not_change_report_bytes(tmp_path):
    pack = _copy_strict(tmp_path)
    args = [str(FIXTURES / "cja_snapshot_messy.json"), "--rubric", str(pack)]
    first = [*args, "--output", str(tmp_path / "a.html"), "--json", str(tmp_path / "a.json")]
    assert main(first) == SUCCESS

    meta = yaml.safe_load((pack / "_meta.yaml").read_text(encoding="utf-8"))
    meta["x_owner"] = "analytics"
    (pack / "_meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")
    for category_file in sorted(pack.glob("[!_]*.yaml")):
        content = yaml.safe_load(category_file.read_text(encoding="utf-8"))
        content["x_reviewed"] = "2026-10-27"
        for rule in content["rules"]:
            rule["x_ticket"] = "SDR-1"
            rule.setdefault("params", {})["x_why"] = "note"
        category_file.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    second = [*args, "--output", str(tmp_path / "b.html"), "--json", str(tmp_path / "b.json")]
    assert main(second) == SUCCESS

    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert (tmp_path / "a.html").read_bytes() == (tmp_path / "b.html").read_bytes()


@pytest.mark.parametrize(
    "flag",
    [
        "--dataview",
        "--rsid",
        "--at",
        "--rubric",
        "--pack",
        "--output",
        "--json",
        "--suppress-config",
        "--distribution-data",
        "--fail-below",
    ],
)
def test_cli_rejects_empty_option_values(tmp_path, capsys, monkeypatch, flag):
    monkeypatch.chdir(tmp_path)
    snapshot = [] if flag in ("--dataview", "--rsid") else [str(FIXTURES / "cja_snapshot_clean.json")]

    rc = main([*snapshot, flag, ""])

    assert rc == RUNTIME_ERROR
    assert capsys.readouterr().err == f"error: {flag} requires a non-empty value\n"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "inputs",
    [
        [str(FIXTURES / "cja_snapshot_clean.json")],
        ["-"],
        ["--rsid", "prod.rsid"],
        ["--dataview", "dv_prod"],
    ],
)
def test_cli_rejects_at_outside_directory_mode(tmp_path, capsys, monkeypatch, inputs):
    import sdr_grader.cli.main as cli_main

    def _no_shell_out(*_args, **_kwargs):
        raise AssertionError("--at must be rejected before shelling out")

    monkeypatch.setattr(cli_main, "shell_aa", _no_shell_out)
    monkeypatch.setattr(cli_main, "shell_cja", _no_shell_out)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("{}"))

    rc = main([*inputs, "--at", "2026-04-25", "--output", str(tmp_path / "out.html")])

    assert rc == RUNTIME_ERROR
    assert capsys.readouterr().err == "error: --at requires a snapshot directory\n"
    assert not (tmp_path / "out.html").exists()


@pytest.mark.parametrize(
    "pack",
    ["../packs/strict", "__pycache__", "strict/", "./strict", "STRICT", "missing"],
)
def test_cli_pack_accepts_only_bundled_pack_names(tmp_path, capsys, pack):
    rc = main([str(FIXTURES / "cja_snapshot_clean.json"), "--pack", pack, "--output", str(tmp_path / "o.html")])

    assert rc == RUNTIME_ERROR
    assert capsys.readouterr().err == (
        f"error: bundled pack {pack!r} not found; choose one of: aa-admin, pragmatic, "
        "strict, or pass --rubric PATH to use a custom pack.\n"
    )
    assert not (tmp_path / "o.html").exists()


@pytest.mark.parametrize("pack", ["aa-admin", "pragmatic", "strict"])
def test_cli_pack_loads_each_bundled_pack_by_name(tmp_path, pack):
    snapshot = "aa_snapshot_clean.json" if pack == "aa-admin" else "cja_snapshot_clean.json"

    rc = main([str(FIXTURES / snapshot), "--pack", pack, "--output", str(tmp_path / "o.html"), "--quiet"])

    assert rc in (SUCCESS, GRADE_BELOW_THRESHOLD)


def _aa_snapshot_with_degraded_classifications(path: Path) -> Path:
    snapshot = json.loads((FIXTURES / "aa_snapshot_clean.json").read_text(encoding="utf-8"))
    snapshot["fetch_status"] = {"classifications": {"status": "degraded", "expansion_level": None}}
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


_DEGRADED_WARNING = (
    "warning [aa-fetch-status]: aa_auto_sdr reported the classifications fetch as degraded; "
    "classification tags may be missing, so findings about untagged dimensions can be overstated\n"
)


def test_cli_warns_about_a_degraded_aa_fetch_without_changing_the_report(tmp_path, capsys):
    degraded = _aa_snapshot_with_degraded_classifications(tmp_path / "degraded.json")

    rc_clean = main([str(FIXTURES / "aa_snapshot_clean.json"), "--json", str(tmp_path / "clean.json"), "--output", str(tmp_path / "clean.html"), "--quiet"])
    capsys.readouterr()
    rc = main([str(degraded), "--json", str(tmp_path / "degraded-report.json"), "--output", str(tmp_path / "degraded.html"), "--quiet"])

    assert rc == rc_clean
    assert capsys.readouterr().err == _DEGRADED_WARNING
    clean_report = json.loads((tmp_path / "clean.json").read_text(encoding="utf-8"))
    degraded_report = json.loads((tmp_path / "degraded-report.json").read_text(encoding="utf-8"))
    for key in ("grade", "overall_pct", "categories", "findings"):
        assert degraded_report[key] == clean_report[key]


def test_cli_trend_warns_once_about_a_degraded_aa_fetch(tmp_path, capsys):
    directory = tmp_path / "trend"
    directory.mkdir()
    _aa_snapshot_with_degraded_classifications(directory / "snap_2026-04-01.json")
    _aa_snapshot_with_degraded_classifications(directory / "snap_2026-04-02.json")

    rc = main([str(directory), "--trend", "--output", str(tmp_path / "trend.html"), "--quiet"])

    assert rc == SUCCESS
    assert capsys.readouterr().err == _DEGRADED_WARNING


def test_extra_input_accepts_a_utf8_bom_like_snapshot_files(tmp_path):
    from types import SimpleNamespace

    from sdr_grader.cli.main import _attach_extra_inputs

    source = tmp_path / "usage.json"
    source.write_bytes(b"\xef\xbb\xbf" + json.dumps({"rows": [1, 2]}).encode("utf-8"))
    impl = SimpleNamespace(supplementary_data={})

    _attach_extra_inputs(impl, [f"usage={source}"])

    assert impl.supplementary_data == {"usage": {"rows": [1, 2]}}

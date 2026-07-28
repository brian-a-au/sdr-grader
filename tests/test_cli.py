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
from sdr_grader.cli.main import main
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


def test_cli_adapter_error_does_not_echo_snapshot_values_or_private_path(
    tmp_path, capsys
):
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
        Path(__file__).resolve().parent.parent
        / "src"
        / "sdr_grader"
        / "rules"
        / "packs"
        / "strict"
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

    def fail_render(_report):
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


@pytest.mark.parametrize("sibling_kind", ["unrelated", "mixed", "malformed", "none"])
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
        ("aa", "99.0.0"),
    ],
)
def test_cli_warns_once_for_newer_generator_without_snapshot_data(
    tmp_path,
    capsys,
    platform,
    version,
):
    snapshot = json.loads(
        (FIXTURES / f"{platform}_snapshot_messy.json").read_text(
            encoding="utf-8"
        )
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
        ("cja", "3.5.17"),
        ("cja", "3.5.0"),
        ("cja", "unparseable"),
        ("aa", "1.18.0"),
        ("aa", "1.17.0"),
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
        (FIXTURES / f"{platform}_snapshot_messy.json").read_text(
            encoding="utf-8"
        )
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

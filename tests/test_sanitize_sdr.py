"""Privacy-boundary tests for the standalone snapshot sanitizer."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

from sdr_grader.adapters.aa import adapt as adapt_aa
from sdr_grader.adapters.cja import adapt as adapt_cja

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "sanitize_sdr.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_sanitizer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sanitize_sdr_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sanitize_sdr = _load_sanitizer()


TENANT_ID = "dv_PRIVATE_TENANT_7"
TENANT_NAME = "Private Customer Analytics"
OWNER = "owner.private@example.com"
USER_CANARY = "Project-Sunrise"
PATH_CANARY = "PRIVATE-PATH-CANARY"


def _patterns(*values: str) -> list[re.Pattern[str]]:
    return [re.compile(re.escape(value), re.IGNORECASE) for value in values]


def _cja_snapshot() -> dict:
    return {
        "metadata": {
            "Data View ID": TENANT_ID,
            "Data View Name": TENANT_NAME,
        },
        "data_view": {
            "data_view_id": TENANT_ID,
            "data_view_name": TENANT_NAME,
        },
        "metrics": [
            {
                "id": "metrics/orders",
                "name": "Orders",
                "description": f"Keep scoring detail; redact {USER_CANARY}.",
                "owner": OWNER,
                "extension": {
                    f"lookup-{TENANT_ID}": f"https://example.invalid/{TENANT_ID}",
                    "owner_id": OWNER,
                },
            }
        ],
        "dimensions": [],
    }


def test_cja_sanitizer_recurses_through_keys_values_and_is_idempotent() -> None:
    cleaned = sanitize_sdr.sanitize(
        _cja_snapshot(),
        platform="cja",
        redact_patterns=_patterns(USER_CANARY),
    )
    serialized = json.dumps(cleaned, ensure_ascii=False)

    for canary in (TENANT_ID, TENANT_NAME, OWNER, USER_CANARY):
        assert canary.casefold() not in serialized.casefold()
    assert "Keep scoring detail" in serialized
    assert "[redacted]" in serialized

    second = sanitize_sdr.sanitize(
        cleaned,
        platform="cja",
        redact_patterns=_patterns(USER_CANARY),
    )
    assert second == cleaned


def test_aa_sanitizer_replaces_nested_owner_and_tenant_references() -> None:
    snapshot = {
        "report_suite": {
            "rsid": "private.prod",
            "name": "Private Production",
            "parent_rsid": "private.global",
        },
        "dimensions": [
            {
                "id": "variables/evar1",
                "owner_id": 918273,
                "extension": {
                    "private.prod": "private.global",
                    "owner": OWNER,
                },
            }
        ],
        "metrics": [],
    }

    cleaned = sanitize_sdr.sanitize(snapshot, platform="aa", redact_patterns=[])
    serialized = json.dumps(cleaned)

    for canary in ("private.prod", "Private Production", "private.global", OWNER, "918273"):
        assert canary.casefold() not in serialized.casefold()
    assert sanitize_sdr.sanitize(cleaned, platform="aa", redact_patterns=[]) == cleaned


def test_short_numeric_owner_does_not_change_unrelated_numbers() -> None:
    snapshot = {
        "report_suite": {"rsid": "suite"},
        "dimensions": [{"id": "evar1", "owner_id": 1, "precision": 1}],
        "metrics": [],
    }

    cleaned = sanitize_sdr.sanitize(snapshot, platform="aa", redact_patterns=[])

    assert isinstance(cleaned["dimensions"][0]["owner_id"], int)
    assert cleaned["dimensions"][0]["owner_id"] < 0
    assert cleaned["dimensions"][0]["precision"] == 1
    assert sanitize_sdr.sanitize(cleaned, platform="aa", redact_patterns=[]) == cleaned


@pytest.mark.parametrize(
    ("platform", "fixture_name", "adapter"),
    [
        ("aa", "aa_snapshot_messy.json", adapt_aa),
        ("cja", "cja_snapshot_messy.json", adapt_cja),
    ],
)
def test_public_fixture_candidate_remains_gradable_and_idempotent(
    platform: str,
    fixture_name: str,
    adapter,
) -> None:
    snapshot = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))

    cleaned = sanitize_sdr.sanitize(
        snapshot,
        platform=platform,
        redact_patterns=[],
    )

    implementation = adapter(cleaned)
    assert implementation.platform == platform
    assert (
        sanitize_sdr.sanitize(
            cleaned,
            platform=platform,
            redact_patterns=[],
        )
        == cleaned
    )


@pytest.mark.parametrize(
    ("limit_name", "value", "error_code"),
    [
        (
            "MAX_DEPTH",
            {"report_suite": {"rsid": "x"}, "dimensions": [[[[]]]], "metrics": []},
            "structure-too-deep",
        ),
        (
            "MAX_COLLECTION_ITEMS",
            {"report_suite": {"rsid": "x"}, "dimensions": [1, 2, 3], "metrics": []},
            "collection-too-large",
        ),
        (
            "MAX_STRING_LENGTH",
            {"report_suite": {"rsid": "xxxx"}, "dimensions": [], "metrics": []},
            "string-too-long",
        ),
    ],
)
def test_structure_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    value: dict,
    error_code: str,
) -> None:
    monkeypatch.setattr(sanitize_sdr, limit_name, 2)
    with pytest.raises(sanitize_sdr.SanitizationError, match=error_code):
        sanitize_sdr.sanitize(value, platform="aa", redact_patterns=[])


def test_main_writes_private_review_candidate_without_echoing_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private_dir = tmp_path / PATH_CANARY
    private_dir.mkdir()
    source = private_dir / f"{TENANT_ID}.json"
    destination = private_dir / f"{PATH_CANARY}-output.json"
    source.write_text(json.dumps(_cja_snapshot()), encoding="utf-8")

    assert (
        sanitize_sdr.main(
            [
                str(source),
                "--platform",
                "cja",
                "--output",
                str(destination),
                "--redact",
                USER_CANARY,
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert PATH_CANARY not in captured.out + captured.err
    assert TENANT_ID not in captured.out + captured.err
    assert "restricted review candidate" in captured.out
    assert "sha256:" in captured.out
    assert "manual review required" in captured.out
    assert "anonym" not in captured.out.casefold()
    assert destination.exists()
    if os.name == "posix":
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "payload",
    [
        '{"metadata":{"Data View ID":"secret"},"metadata":{}}',
        '{"metadata": ',
        '{"metadata":{"Data View ID":NaN},"metrics":[],"dimensions":[]}',
    ],
)
def test_invalid_or_ambiguous_json_leaves_no_output_and_no_excerpt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: str,
) -> None:
    source = tmp_path / f"{PATH_CANARY}.json"
    destination = tmp_path / "candidate.json"
    source.write_text(payload, encoding="utf-8")

    assert sanitize_sdr.main([str(source), "--platform", "cja", "--output", str(destination)]) != 0

    captured = capsys.readouterr()
    assert not destination.exists()
    assert PATH_CANARY not in captured.err
    assert payload not in captured.err
    assert "sanitize error [" in captured.err


def test_input_byte_limit_fails_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "candidate.json"
    source.write_text(json.dumps(_cja_snapshot()), encoding="utf-8")
    monkeypatch.setattr(sanitize_sdr, "MAX_INPUT_BYTES", 32)

    assert sanitize_sdr.main([str(source), "--platform", "cja", "--output", str(destination)]) != 0

    assert not destination.exists()
    assert "input-too-large" in capsys.readouterr().err


def test_atomic_write_failure_preserves_existing_destination_and_cleans_stage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "candidate.json"
    source.write_text(json.dumps(_cja_snapshot()), encoding="utf-8")
    destination.write_text("existing", encoding="utf-8")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError(PATH_CANARY)

    monkeypatch.setattr(sanitize_sdr.os, "replace", fail_replace)
    assert sanitize_sdr.main([str(source), "--platform", "cja", "--output", str(destination)]) != 0

    assert destination.read_text(encoding="utf-8") == "existing"
    assert not list(tmp_path.glob(".sanitize-sdr-*"))
    assert PATH_CANARY not in capsys.readouterr().err


def test_residue_check_rejects_user_supplied_canary() -> None:
    with pytest.raises(sanitize_sdr.SanitizationError, match="residue-detected"):
        sanitize_sdr._assert_no_residue(  # noqa: SLF001 - direct boundary proof
            {"description": USER_CANARY},
            replacements=sanitize_sdr._replacement_plan([]),  # noqa: SLF001
            redact_patterns=_patterns(USER_CANARY),
        )

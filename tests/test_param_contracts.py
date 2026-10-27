"""Per-check parameter contracts and fixed-key validation (core arc PR 2)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.input.adapt import adapt_snapshot
from sdr_grader.rules import params as P
from sdr_grader.rules.engine import RuleContext
from sdr_grader.rules.registry import (
    _import_all_checks,
    get_check,
    get_contract,
    register_check,
    registered_names,
)

LABEL = "naming.yaml NAME-T01: 'key'"


@pytest.mark.parametrize(
    ("spec", "value"),
    [
        (P.RATIO, 0),
        (P.RATIO, 1.0),
        (P.RATIO, 0.5),
        (P.NON_NEGATIVE_FLOAT, 0),
        (P.NON_NEGATIVE_FLOAT, 75.5),
        (P.NON_NEGATIVE_INT, 0),
        (P.NON_NEGATIVE_INT, 90),
        (P.REGEX, "^[a-z]+$"),
        (P.TARGET, "dimensions"),
        (P.TARGETS, ["metrics", "segments"]),
        (P.OPTIONAL_STRING, "core"),
        (P.OPTIONAL_STRING, None),
        (P.STRING_LIST, []),
        (P.STRING_LIST, ["linear"]),
        (P.OPTIONAL_STRING_LIST, None),
        (P.OPTIONAL_STRING_LIST, ["page"]),
        (P.SYNONYM_GROUPS, None),
        (P.SYNONYM_GROUPS, [["visit", "session"]]),
        (P.OPTIONAL_TIMESTAMP, None),
        (P.OPTIONAL_TIMESTAMP, "2026-01-01"),
        (P.OPTIONAL_TIMESTAMP, dt.date(2026, 1, 1)),
        (P.OPTIONAL_TIMESTAMP, dt.datetime(2026, 1, 1, tzinfo=dt.UTC)),
        (P.LITERAL_BOOLEAN, True),
        (P.LITERAL_BOOLEAN, False),
        (P.TEXT_BOOLEAN, True),
        (P.TEXT_BOOLEAN, "false"),
        (P.TEXT_BOOLEAN, None),
    ],
)
def test_specs_accept_valid_values(spec, value):
    spec.check(value, label=LABEL)


@pytest.mark.parametrize(
    ("spec", "value", "fragment"),
    [
        (P.RATIO, True, "must be a finite number in [0, 1]"),
        (P.RATIO, 1.5, "must be a finite number in [0, 1]"),
        (P.RATIO, float("nan"), "must be a finite number in [0, 1]"),
        (P.RATIO, 10**400, "must be a finite number in [0, 1]"),
        (P.NON_NEGATIVE_FLOAT, -1, "must be a finite number in [0, inf]"),
        (P.NON_NEGATIVE_INT, 2.5, "must be an integer in [0, inf]"),
        (P.NON_NEGATIVE_INT, 5.0, "must be an integer in [0, inf]"),
        (P.NON_NEGATIVE_INT, True, "must be an integer in [0, inf]"),
        (P.REGEX, 7, "must be a string"),
        (P.REGEX, "[", "is not a valid regex"),
        (P.TARGET, "dimensons", "did you mean 'dimensions'"),
        (P.TARGET, ["dimensions"], "must be one of"),
        (P.TARGETS, [], "must be a non-empty list of strings"),
        (P.TARGETS, "metrics", "must be a non-empty list of strings"),
        (P.TARGETS, ["raw"], "unknown name 'raw'"),
        (P.OPTIONAL_STRING, 3, "must be a string"),
        (P.STRING_LIST, "linear", "must be a list of strings"),
        (P.STRING_LIST, [1], "must be a list of strings"),
        (P.SYNONYM_GROUPS, [["visit"]], "at least 2 non-empty strings"),
        (P.SYNONYM_GROUPS, [["visit", ""]], "at least 2 non-empty strings"),
        (P.SYNONYM_GROUPS, ["visit", "session"], "at least 2 non-empty strings"),
        (P.SYNONYM_GROUPS, "visit session", "at least 2 non-empty strings"),
        (P.OPTIONAL_TIMESTAMP, "not a date", "must be a date or timestamp"),
        (P.OPTIONAL_TIMESTAMP, 20260101, "must be a date or timestamp"),
        (P.LITERAL_BOOLEAN, "true", "must be a boolean"),
        (P.LITERAL_BOOLEAN, 1, "must be a boolean"),
        (P.TEXT_BOOLEAN, "yes", "expected boolean"),
    ],
)
def test_specs_reject_invalid_values(spec, value, fragment):
    with pytest.raises(RubricValidationError) as exc:
        spec.check(value, label=LABEL)
    assert LABEL in str(exc.value)
    assert fragment in str(exc.value)


@pytest.mark.parametrize(
    "spec",
    [
        P.RATIO,
        P.NON_NEGATIVE_FLOAT,
        P.NON_NEGATIVE_INT,
        P.REGEX,
        P.TARGET,
        P.TARGETS,
        P.STRING_LIST,
        P.LITERAL_BOOLEAN,
    ],
)
def test_non_nullable_specs_reject_null(spec):
    with pytest.raises(RubricValidationError):
        spec.check(None, label=LABEL)


def test_reject_unknown_keys_skips_allowed_and_extension_keys():
    P.reject_unknown_keys({"a": 1, "x_note": "kept", "x_": 0}, {"a", "b"}, where="naming.yaml")


def test_reject_unknown_keys_reports_first_in_order_with_hint():
    with pytest.raises(RubricValidationError) as exc:
        P.reject_unknown_keys(
            {"zzz": 1, "severty": 2}, {"severity", "name"}, where="naming.yaml NAME-T01"
        )
    message = str(exc.value)
    assert message.startswith("naming.yaml NAME-T01: unknown key 'severty'")
    assert "did you mean 'severity'?" in message
    assert "'zzz'" not in message
    assert "x_" in message


def test_reject_unknown_keys_gives_no_hint_for_unrelated_key():
    with pytest.raises(RubricValidationError) as exc:
        P.reject_unknown_keys({"qqqq": 1}, {"severity"}, where="w")
    assert "did you mean" not in str(exc.value)


def test_extension_prefix_is_case_sensitive():
    with pytest.raises(RubricValidationError, match="'X_note'"):
        P.reject_unknown_keys({"X_note": 1}, set(), where="w")


def test_reject_unknown_keys_handles_non_string_keys():
    with pytest.raises(RubricValidationError) as exc:
        P.reject_unknown_keys({True: 1, 2: 2, "b": 3}, {"b"}, where="w")
    assert "unknown key" in str(exc.value)


def test_unknown_key_message_is_bounded_and_escaped():
    key = "\x1b[2J" + "k" * 10_000
    with pytest.raises(RubricValidationError) as exc:
        P.reject_unknown_keys({key: 1}, {"a"}, where="w")
    message = str(exc.value)
    assert "\x1b" not in message
    assert len(message) < 500


def test_validate_params_scopes_rejects_and_checks_aliases():
    specs = {"threshold": P.RATIO, "flag": P.TEXT_BOOLEAN, "Flag Alias": P.TEXT_BOOLEAN}
    groups = [("flag", "Flag Alias")]
    P.validate_params({"threshold": 0.2, "x_note": "n"}, specs, groups, where="f R")
    with pytest.raises(RubricValidationError, match="f R params: unknown key 'treshold'"):
        P.validate_params({"treshold": 0.2}, specs, groups, where="f R")
    with pytest.raises(RubricValidationError, match="f R: 'threshold' must be"):
        P.validate_params({"threshold": 2}, specs, groups, where="f R")
    with pytest.raises(RubricValidationError, match="conflicting boolean aliases"):
        P.validate_params({"flag": True, "Flag Alias": "false"}, specs, groups, where="f R")


FIXTURES = Path(__file__).parent / "fixtures"


class _RecordingParams(dict):
    """Empty params that record every key a check asks for."""

    def __init__(self) -> None:
        super().__init__()
        self.read: set[str] = set()

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.read.add(key)
        return super().__contains__(key)


def _honesty_impls():
    impls = [
        adapt_snapshot(
            json.loads((FIXTURES / name).read_text(encoding="utf-8")),
            source=name,
            platform_override=None,
        )
        for name in ("cja_snapshot_messy.json", "aa_snapshot_messy.json", "cja_snapshot_clean.json")
    ]
    # launch_required_data_elements returns before reading params without launch data.
    impls.append(
        dataclasses.replace(impls[0], supplementary_data={"launch": {"data_elements": []}})
    )
    return impls


def test_every_check_declares_exactly_the_params_it_reads():
    _import_all_checks()
    impls = _honesty_impls()
    mismatches = {}
    for name in registered_names():
        read: set[str] = set()
        for impl in impls:
            params = _RecordingParams()
            ctx = RuleContext(
                rule_id="T",
                rule_name="T",
                severity="low",
                category="naming_conventions",
                platforms=["cja", "aa"],
                params=params,
                rationale="",
                remediation="",
            )
            get_check(name)(impl, ctx)
            read |= params.read
        declared = set(get_contract(name).params)
        if read != declared:
            mismatches[name] = {"read": sorted(read), "declared": sorted(declared)}
    assert mismatches == {}


def test_alias_groups_must_name_declared_params():
    with pytest.raises(ValueError, match="alias group"):
        register_check("_test_bad_alias", params={"a": P.TEXT_BOOLEAN}, alias_groups=[("a", "b")])


def test_contract_lookup_for_unknown_check_raises_key_error():
    with pytest.raises(KeyError):
        get_contract("no_such_check")


DOCS = Path(__file__).resolve().parent.parent / "docs"
_START = "<!-- param-contracts:start -->"
_END = "<!-- param-contracts:end -->"


def _contract_rows() -> list[str]:
    _import_all_checks()
    return [
        f"| `{name}` | `{key}` | {spec.summary} |"
        for name in registered_names()
        for key, spec in sorted(get_contract(name).params.items())
    ]


def test_rubric_format_param_table_matches_registry():
    text = (DOCS / "RUBRIC_FORMAT.md").read_text(encoding="utf-8")
    assert _START in text and _END in text
    body = text.split(_START, 1)[1].split(_END, 1)[0]
    rows = [line for line in body.splitlines() if line.startswith("| `")]
    assert rows == _contract_rows()

"""Declared parameter contracts for registered checks, and fixed-key checks.

A check declares the params it reads when it registers. The rubric loader
validates YAML params against that declaration so a typo fails loudly
instead of silently disabling the check. String keys starting with x_ are a
reserved extension point: never validated, never read by any check.
"""

from __future__ import annotations

import difflib
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from sdr_grader.core.booleans import boolean_aliases, parse_boolean
from sdr_grader.core.exceptions import RubricValidationError
from sdr_grader.core.timeparse import parse_timestamp
from sdr_grader.rules.yaml_io import describe_value

EXTENSION_PREFIX = "x_"
KNOWN_TARGETS = frozenset(
    {"metrics", "dimensions", "derived_fields", "calculated_metrics", "segments"}
)

Validator = Callable[[Any, str], None]


@dataclass(frozen=True)
class ParamSpec:
    """One param's accepted values. `summary` is the RUBRIC_FORMAT.md text."""

    summary: str
    validate: Validator
    nullable: bool = False

    def check(self, value: Any, *, label: str) -> None:
        if value is None and self.nullable:
            return
        self.validate(value, label)


def _hint(key: Any, choices: Iterable[str]) -> str:
    if not isinstance(key, str):
        return ""
    match = difflib.get_close_matches(key, sorted(choices), n=1)
    return f"; did you mean {match[0]!r}?" if match else ""


def _number(kind: type, lo: float, hi: float | None) -> Validator:
    kind_text = "a finite number" if kind is float else "an integer"
    hi_text = "inf" if hi is None else f"{hi:g}"

    def validate(value: Any, label: str) -> None:
        message = f"{label} must be {kind_text} in [{lo:g}, {hi_text}]"
        accepted = (int,) if kind is int else (int, float)
        if isinstance(value, bool) or not isinstance(value, accepted):
            raise RubricValidationError(message)
        try:
            # float() rejects ints too large for a float (e.g. 400 digits)
            number = float(value)
        except OverflowError as exc:
            raise RubricValidationError(message) from exc
        if not math.isfinite(number) or number < lo or (hi is not None and number > hi):
            raise RubricValidationError(message)

    return validate


def _regex(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise RubricValidationError(f"{label} must be a string")
    try:
        re.compile(value)
    except re.error as exc:
        raise RubricValidationError(
            f"{label} is not a valid regex ({describe_value(exc.msg)} at position {exc.pos})"
        ) from exc


def _target(value: Any, label: str) -> None:
    if not isinstance(value, str) or value not in KNOWN_TARGETS:
        raise RubricValidationError(
            f"{label} must be one of {sorted(KNOWN_TARGETS)!r}; got "
            f"{describe_value(value)}{_hint(value, KNOWN_TARGETS)}"
        )


def _targets(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(t, str) for t in value):
        raise RubricValidationError(f"{label} must be a non-empty list of strings")
    unknown = sorted(set(value) - KNOWN_TARGETS)
    if unknown:
        raise RubricValidationError(
            f"{label} has unknown name {describe_value(unknown[0])}"
            f"{_hint(unknown[0], KNOWN_TARGETS)}; expected names from {sorted(KNOWN_TARGETS)!r}"
        )


def _string(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise RubricValidationError(f"{label} must be a string")


def _string_list(value: Any, label: str) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RubricValidationError(f"{label} must be a list of strings")


def _synonym_groups(value: Any, label: str) -> None:
    message = f"{label} must be a list of groups, each a list of at least 2 non-empty strings"
    if not isinstance(value, list):
        raise RubricValidationError(message)
    for group in value:
        if (
            not isinstance(group, list)
            or len(group) < 2
            or not all(isinstance(w, str) and w.strip() for w in group)
        ):
            raise RubricValidationError(message)


def _timestamp(value: Any, label: str) -> None:
    # YAML loads unquoted dates as date/datetime; checks call str() first.
    # The checks treat "" like null (not given), so accept it the same way.
    if value == "":
        return
    if not isinstance(value, (str, date)) or parse_timestamp(str(value)) is None:
        raise RubricValidationError(f"{label} must be a date or timestamp the grader can parse")


def _literal_boolean(value: Any, label: str) -> None:
    if not isinstance(value, bool):
        raise RubricValidationError(f"{label} must be a boolean")


def _text_boolean(value: Any, label: str) -> None:
    parse_boolean(value, path=label, error=RubricValidationError)


RATIO = ParamSpec("number in [0, 1]", _number(float, 0.0, 1.0))
NON_NEGATIVE_FLOAT = ParamSpec("number >= 0", _number(float, 0.0, None))
NON_NEGATIVE_INT = ParamSpec("integer >= 0", _number(int, 0, None))
REGEX = ParamSpec("regular expression string", _regex)
TARGET = ParamSpec("one collection name", _target)
TARGETS = ParamSpec("non-empty list of collection names", _targets)
OPTIONAL_STRING = ParamSpec("string, or null", _string, nullable=True)
STRING_LIST = ParamSpec("list of strings", _string_list)
OPTIONAL_STRING_LIST = ParamSpec("list of strings, or null", _string_list, nullable=True)
SYNONYM_GROUPS = ParamSpec(
    "list of word groups (2+ words each), or null", _synonym_groups, nullable=True
)
OPTIONAL_TIMESTAMP = ParamSpec("date or timestamp, or null or empty", _timestamp, nullable=True)
LITERAL_BOOLEAN = ParamSpec("true or false", _literal_boolean)
TEXT_BOOLEAN = ParamSpec('true or false (or "true"/"false"), or null', _text_boolean, nullable=True)


def reject_unknown_keys(mapping: Mapping[Any, Any], allowed: Iterable[str], *, where: str) -> None:
    """Fail on the first key that is neither allowed nor an x_ extension."""
    allowed_set = frozenset(allowed)
    unknown = [
        key
        for key in mapping
        if not (isinstance(key, str) and (key in allowed_set or key.startswith(EXTENSION_PREFIX)))
    ]
    if not unknown:
        return
    # Order by bounded text so mixed key types (YAML `yes:`, `1:`) sort safely.
    first = min(unknown, key=describe_value)
    raise RubricValidationError(
        f"{where}: unknown key {describe_value(first)}{_hint(first, allowed_set)}; "
        f"expected keys from {sorted(allowed_set)!r} (prefix custom keys with "
        f"{EXTENSION_PREFIX!r})"
    )


def validate_params(
    params: Mapping[Any, Any],
    specs: Mapping[str, ParamSpec],
    alias_groups: Iterable[tuple[str, ...]],
    *,
    where: str,
) -> None:
    """Validate one rule's params against its check's declared contract."""
    reject_unknown_keys(params, specs, where=f"{where} params")
    # Alias groups use the check's own run-time path ("params.<key>"), so these
    # diagnostics stay identical to earlier releases' published text.
    for group in alias_groups:
        boolean_aliases(params, group, path="params", error=RubricValidationError)
    for key in sorted(specs):
        if key in params:
            specs[key].check(params[key], label=f"{where}: '{key}'")

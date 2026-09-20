"""Validated, offline AA administration evidence and rule applicability.

Unknown observation tokens are unassessed, never defaults. Business expectations
are independent of observed settings. No inventory-wide coverage is implied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.models import Implementation
from sdr_grader.core.timeparse import parse_timestamp

ALLOCATION = frozenset(
    {
        "most_recent_last",
        "original_value_first",
        "linear",
        "linear_to_items",
        "merchandising_first",
        "merchandising_last",
    }
)
EXPIRATION = frozenset(
    {
        "visit",
        "page_view",
        "never",
        "minute",
        "hour",
        "day",
        "week",
        "month",
        "quarter",
        "year",
        "purchase",
        "product_view",
        "cart_open",
        "cart_checkout",
        "cart_add",
        "cart_remove",
        "cart_view",
        "event",
    }
)
TOKENS = {
    "allocation": ALLOCATION,
    "expiration": EXPIRATION,
    "merchandising_syntax": frozenset({"product", "conversion_variable"}),
    "event_type": frozenset({"counter", "numeric", "currency"}),
    "serialization": frozenset({"always", "once_per_visit", "use_event_id"}),
}
FIELDS = {
    "evars": {
        "allocation",
        "expiration",
        "expiration_days",
        "merchandising_syntax",
        "binding_events",
    },
    "events": {"event_type", "serialization"},
}
AA_CHECKS = {
    "aa_allocation_expiration": ("evars", {"allocation", "expiration", "expiration_days"}),
    "aa_event_type": ("events", {"event_type"}),
    "aa_serialization": ("events", {"serialization"}),
    "aa_merchandising": ("evars", {"merchandising_syntax", "binding_events"}),
}


@dataclass(frozen=True)
class AAAdminAssessment:
    targets: tuple[str, ...] = ()
    mismatches: tuple[str, ...] = ()
    reason: str = ""

    @property
    def not_assessed(self) -> bool:
        return bool(self.reason)


def _invalid() -> None:
    # Do not echo supplied settings, provenance, identifiers, or credentials.
    raise InvalidSnapshotError(
        "aa_admin: malformed, duplicate, conflicting, or mismatched evidence"
    )


def _object(value: Any, allowed: set[str], required: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict) or set(value) - allowed or not required <= set(value):
        _invalid()
    return value


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _settings(record: dict, kind: str, *, expected: bool) -> dict:
    result = {}
    for key, value in record.items():
        if key == "id":
            continue
        if key not in FIELDS[kind]:
            _invalid()
        if key == "binding_events":
            if (
                not isinstance(value, list)
                or any(not isinstance(v, str) or not re.fullmatch(r"metrics/\S+", v) for v in value)
                or len(value) != len(set(value))
            ):
                _invalid()
            value = tuple(sorted(value))
        elif key == "expiration_days":
            if type(value) is not int or value <= 0:
                _invalid()
        elif not _text(value) or (expected and value not in TOKENS[key]):
            _invalid()
        result[key] = value
    return result


def _records(value: Any, kind: str, *, expected: bool) -> dict[str, dict]:
    if not isinstance(value, list):
        _invalid()
    result = {}
    pattern = r"variables/evar[1-9][0-9]*" if kind == "evars" else r"metrics/event[1-9][0-9]*"
    for record in value:
        record = _object(record, FIELDS[kind] | {"id"}, {"id"})
        identifier = record["id"]
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(pattern, identifier)
            or identifier in result
        ):
            _invalid()
        result[identifier] = _settings(record, kind, expected=expected)
    return result


def _merge(target: dict, source: dict) -> None:
    if any(key in target and target[key] != value for key, value in source.items()):
        _invalid()
    target.update(source)


def _evidence(impl: Implementation) -> tuple[dict, dict] | None:
    if "aa_admin" not in impl.supplementary_data:
        return None
    document = _object(
        impl.supplementary_data["aa_admin"],
        {
            "schema_version",
            "platform",
            "report_suite_id",
            "captured_at",
            "source",
            "observations",
            "expectations",
        },
        {
            "schema_version",
            "platform",
            "report_suite_id",
            "captured_at",
            "source",
            "observations",
            "expectations",
        },
    )
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["platform"] != "aa"
        or document["report_suite_id"] != impl.instance_id
        or not _text(document["source"])
        or parse_timestamp(document["captured_at"]) is None
    ):
        _invalid()
    sections = []
    for section in ("observations", "expectations"):
        raw = _object(document[section], {"evars", "events"})
        sections.append(
            {
                kind: _records(raw.get(kind, []), kind, expected=section == "expectations")
                for kind in FIELDS
            }
        )
    observed, expected = sections
    seen = set()
    for component in impl.dimensions:
        if not re.fullmatch(r"variables/evar[1-9][0-9]*", component.id):
            continue
        if component.id in seen:
            _invalid()
        seen.add(component.id)
        settings = observed["evars"].setdefault(component.id, {})
        for source in component.platform_specific.get("aa_admin_sources", []):
            _merge(settings, _settings(source, "evars", expected=False))
    return observed, expected


def _required(check: str, settings: dict) -> set[str]:
    if check == "aa_allocation_expiration":
        required = {"allocation", "expiration"}
        if settings.get("expiration") == "day":
            required.add("expiration_days")
        return required
    if check == "aa_merchandising":
        required = {"merchandising_syntax", "allocation"}
        if settings.get("merchandising_syntax") == "conversion_variable":
            required.add("binding_events")
        return required
    return AA_CHECKS[check][1]


def assess_aa_admin(impl: Implementation, checks: set[str]) -> dict[str, AAAdminAssessment]:
    """Analyze once per run; exclude entire checks with incomplete declared scope."""
    if not checks:
        return {}
    evidence = _evidence(impl)
    result = {}
    for check in sorted(checks):
        if evidence is None:
            result[check] = AAAdminAssessment(
                reason="aa_admin input absent; settings remain unverified."
            )
            continue
        observed, expected = evidence
        kind, selectors = AA_CHECKS[check]
        targets = tuple(
            sorted(key for key, value in expected[kind].items() if selectors & value.keys())
        )
        missing = not targets
        mismatches = []
        for identifier in targets:
            actual = observed[kind].get(identifier, {})
            wanted = expected[kind][identifier]
            required = _required(check, wanted)
            actual_required = _required(check, actual)
            complete = actual_required <= actual.keys() and required <= wanted.keys()
            supported = all(
                value in TOKENS[key]
                for key, value in actual.items()
                if key in actual_required and key in TOKENS
            )
            if not complete or not supported:
                missing = True
            elif any(actual.get(key) != wanted[key] for key in required):
                mismatches.append(identifier)
        reason = (
            "No declared targets."
            if not targets
            else "Incomplete or unsupported evidence for declared targets; entire rule excluded."
        )
        result[check] = AAAdminAssessment(targets, tuple(mismatches), reason if missing else "")
    return result

"""Shared timestamp parser (spec F4)."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

from sdr_grader.core.timeparse import parse_timestamp, to_utc


def test_parses_utc_offset():
    assert parse_timestamp("2026-05-20T14:00:00+00:00") == datetime(
        2026, 5, 20, 14, 0, 0, tzinfo=UTC
    )


def test_parses_fractional_seconds_with_z():
    assert parse_timestamp("2026-05-20T14:00:00.250Z") == datetime(
        2026, 5, 20, 14, 0, 0, 250000, tzinfo=UTC
    )


def test_parses_space_separator_as_utc():
    assert parse_timestamp("2026-05-20 14:00:00") == datetime(2026, 5, 20, 14, 0, 0, tzinfo=UTC)


def test_parses_date_only():
    assert parse_timestamp("2026-05-20") == datetime(2026, 5, 20, tzinfo=UTC)


def test_normalizes_non_utc_offset_to_utc():
    assert parse_timestamp("2026-05-20T16:00:00+02:00") == datetime(
        2026, 5, 20, 14, 0, 0, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "2026-05-20 10:56:29 PDT",
            datetime(2026, 5, 20, 17, 56, 29, tzinfo=UTC),
        ),
        (
            "2026-05-20 10:56:29 PST",
            datetime(2026, 5, 20, 18, 56, 29, tzinfo=UTC),
        ),
        (
            "2026-05-20 10:56:29.125 PDT",
            datetime(2026, 5, 20, 17, 56, 29, 125000, tzinfo=UTC),
        ),
        (
            "2026-05-20 10:56:29 UTC",
            datetime(2026, 5, 20, 10, 56, 29, tzinfo=UTC),
        ),
        (
            "2026-05-20 10:56:29 GMT",
            datetime(2026, 5, 20, 10, 56, 29, tzinfo=UTC),
        ),
    ],
)
def test_parses_allowlisted_timezone_abbreviations(raw, expected):
    assert parse_timestamp(raw) == expected


def test_unknown_or_ambiguous_timezone_abbreviation_returns_none():
    assert parse_timestamp("2026-05-20 10:56:29 CST") is None
    assert parse_timestamp("2026-05-20 10:56:29 LOCAL") is None
    assert parse_timestamp("not-a-timestamp PDT") is None
    assert parse_timestamp("2026-05-20T10:56:29+01:00 PDT") is None


def test_aware_datetime_normalizes_to_utc():
    assert to_utc(
        datetime(2026, 5, 20, 16, 0, tzinfo=timezone(timedelta(hours=2)))
    ) == datetime(2026, 5, 20, 14, 0, tzinfo=UTC)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="host timezone control is POSIX-specific")
def test_abbreviation_parsing_ignores_host_timezone(monkeypatch):
    original = os.environ.get("TZ")
    try:
        observed = []
        for host_timezone in ("UTC0", "PST8PDT", "JST-9"):
            monkeypatch.setenv("TZ", host_timezone)
            time.tzset()
            observed.append(parse_timestamp("2026-05-20 10:56:29 PDT"))
        assert observed == [datetime(2026, 5, 20, 17, 56, 29, tzinfo=UTC)] * 3
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def test_garbage_returns_none():
    assert parse_timestamp("not a date") is None
    assert parse_timestamp("") is None


def test_non_string_returns_none():
    assert parse_timestamp(None) is None  # type: ignore[arg-type]


def test_grader_resolves_offset_timestamp_to_real_date():
    from sdr_grader.core.grader import _resolve_generated_at

    resolved = _resolve_generated_at("2026-05-20T14:00:00+00:00")
    assert (resolved.year, resolved.month, resolved.day) == (2026, 5, 20)

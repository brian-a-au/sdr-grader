"""Shared timestamp parser (spec F4)."""

from __future__ import annotations

from datetime import UTC, datetime

from sdr_grader.core.timeparse import parse_timestamp


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


def test_garbage_returns_none():
    assert parse_timestamp("not a date") is None
    assert parse_timestamp("") is None


def test_non_string_returns_none():
    assert parse_timestamp(None) is None  # type: ignore[arg-type]


def test_grader_resolves_offset_timestamp_to_real_date():
    from sdr_grader.core.grader import _resolve_generated_at

    resolved = _resolve_generated_at("2026-05-20T14:00:00+00:00")
    assert (resolved.year, resolved.month, resolved.day) == (2026, 5, 20)

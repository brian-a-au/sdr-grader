"""Locale-pinned date rendering and naive-UTC normalization (spec F30, F31)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sdr_grader.render.dates import MONTH_ABBREV, human_date, human_datetime, to_utc


def test_month_table_covers_all_twelve_months():
    expected = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    got = [human_date(datetime(2026, m, 5, tzinfo=UTC))[:3] for m in range(1, 13)]
    assert got == expected == list(MONTH_ABBREV)


def test_human_formats_match_the_report_footer_shape():
    dt = datetime(2026, 4, 25, 9, 14, tzinfo=UTC)
    assert human_datetime(dt) == "Apr 25 2026 · 09:14 UTC"
    assert human_date(dt) == "Apr 25 2026"


def test_day_stays_zero_padded():
    assert human_date(datetime(2026, 4, 5, tzinfo=UTC)) == "Apr 05 2026"


def test_naive_means_utc():
    naive = datetime(2026, 4, 25, 9, 14)
    aware = datetime(2026, 4, 25, 9, 14, tzinfo=UTC)
    assert to_utc(naive) == aware
    assert human_datetime(naive) == human_datetime(aware)


def test_aware_non_utc_converts_instead_of_relabeling():
    plus2 = datetime(2026, 4, 25, 11, 14, tzinfo=timezone(timedelta(hours=2)))
    assert to_utc(plus2) == datetime(2026, 4, 25, 9, 14, tzinfo=UTC)
    assert human_datetime(plus2) == "Apr 25 2026 · 09:14 UTC"


def test_to_utc_is_the_timeparse_function():
    """Spec F45: keep one definition of the naive-means-UTC rule."""
    from sdr_grader.core import timeparse
    from sdr_grader.render import dates

    assert dates.to_utc is timeparse.to_utc

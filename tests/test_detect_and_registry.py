"""Coverage for input.detect.detect_platform and rules.registry edge cases.

Both modules are small, but the failure paths (non-dict input, unknown
platform, duplicate check registration, missing check lookup) are exactly
where future regressions hide if they go untested.
"""

from __future__ import annotations

import pytest

from _rule_test_helpers import impl
from sdr_grader.core.exceptions import UnknownPlatformError
from sdr_grader.input.detect import detect_platform
from sdr_grader.rules.engine import _applies_to_platform
from sdr_grader.rules.registry import get_check, register_check
from sdr_grader.rules.rubric import RuleDefinition

# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------


def test_detect_rejects_non_dict_input():
    """A bare list / string / int isn't a valid snapshot shape."""
    with pytest.raises(UnknownPlatformError, match="not a JSON object"):
        detect_platform(["not", "a", "dict"])


def test_detect_bare_data_view_key_raises_unparseable_shape():
    """A top-level `data_view` key alone is not enough: the CJA adapter
    requires `metadata`, so this shape can never be parsed. detect_platform
    must raise rather than silently claim "cja" (dropped dead fallback)."""
    with pytest.raises(UnknownPlatformError, match="could not auto-detect"):
        detect_platform({"data_view": {"id": "dv_x"}})
    # camelCase variant is equally unparseable.
    with pytest.raises(UnknownPlatformError, match="could not auto-detect"):
        detect_platform({"dataView": {"id": "dv_x"}})


def test_detect_raises_when_no_platform_marker_found():
    """Snapshot with neither CJA nor AA markers must error out so the
    caller can ask the user to pass --platform explicitly."""
    with pytest.raises(UnknownPlatformError, match="could not auto-detect"):
        detect_platform({"unrelated": "shape"})


def test_detect_ambiguous_snapshot_raises():
    snap = {"metadata": {"Data View ID": "dv1"}, "report_suite": {"rsid": "rs1"}}
    with pytest.raises(UnknownPlatformError, match="both"):
        detect_platform(snap)


def test_detect_bare_data_view_key_is_not_enough():
    # The old fallback said "cja" for a shape the CJA adapter can't parse.
    with pytest.raises(UnknownPlatformError):
        detect_platform({"data_view": {}})


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def test_register_check_re_registering_same_function_is_idempotent():
    """Registering the same function object twice under the same name (e.g.
    on module re-import in tests) must no-op rather than raise — modules
    sometimes get reloaded and we don't want that to corrupt the registry."""

    def shared(impl, ctx):
        return []

    decorator = register_check("__test_idempotent_check__")
    decorator(shared)
    # Second registration of the same function object hits the
    # `existing is fn` branch and returns without raising.
    decorator(shared)

    assert get_check("__test_idempotent_check__") is shared


def test_register_check_rejects_distinct_function_under_taken_name():
    """A name collision between two distinct check implementations is a
    bug worth a loud failure — packs would otherwise silently swap behavior."""

    @register_check("__test_collision_check__")
    def first(impl, ctx):
        return []

    with pytest.raises(ValueError, match="already registered"):

        @register_check("__test_collision_check__")
        def second(impl, ctx):
            return []


def test_get_check_unknown_name_raises_with_known_list():
    """KeyError message must include the known-checks list so the caller
    can spot a YAML typo without rereading the registry."""
    with pytest.raises(KeyError, match="no check function registered"):
        get_check("__no_such_check_anywhere__")


def test_platform_agnostic_rule_applies_to_any_implementation():
    rule = RuleDefinition(
        id="TEST-ANY",
        name="Platform agnostic",
        severity="low",
        platforms=[],
        check="unused-in-direct-test",
        category="schema_hygiene",
    )
    assert _applies_to_platform(rule, impl(platform="cja")) is True

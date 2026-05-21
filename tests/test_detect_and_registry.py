"""Coverage for input.detect.detect_platform and rules.registry edge cases.

Both modules are small, but the failure paths (non-dict input, unknown
platform, duplicate check registration, missing check lookup) are exactly
where future regressions hide if they go untested.
"""

from __future__ import annotations

import pytest

from sdr_grader.core.exceptions import UnknownPlatformError
from sdr_grader.input.detect import detect_platform
from sdr_grader.rules.registry import get_check, register_check

# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------


def test_detect_rejects_non_dict_input():
    """A bare list / string / int isn't a valid snapshot shape."""
    with pytest.raises(UnknownPlatformError, match="not a JSON object"):
        detect_platform(["not", "a", "dict"])


def test_detect_falls_back_to_data_view_key_for_cja():
    """Some adapters emit `data_view` at top level instead of nesting under
    `metadata` — detect_platform still resolves these as CJA."""
    assert detect_platform({"data_view": {"id": "dv_x"}}) == "cja"
    # camelCase variant accepted too.
    assert detect_platform({"dataView": {"id": "dv_x"}}) == "cja"


def test_detect_raises_when_no_platform_marker_found():
    """Snapshot with neither CJA nor AA markers must error out so the
    caller can ask the user to pass --platform explicitly."""
    with pytest.raises(UnknownPlatformError, match="could not auto-detect"):
        detect_platform({"unrelated": "shape"})


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

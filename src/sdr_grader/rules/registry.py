"""Check function registry.

Per SPEC §6: rules are YAML; checks are pure Python functions registered by
name via the @register_check decorator. The registry is a global dict;
rubric loading looks up each rule's `check:` field here. This is a function
lookup, not a plugin system — keep it simple.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.render import Finding
    from sdr_grader.rules.engine import RuleContext

CheckFn = Callable[["Implementation", "RuleContext"], list["Finding"]]

_REGISTRY: dict[str, CheckFn] = {}


def register_check(name: str) -> Callable[[CheckFn], CheckFn]:
    """Register a check function under the given name.

    Raises if the name is already registered to keep packs unambiguous.
    """

    def decorator(fn: CheckFn) -> CheckFn:
        if name in _REGISTRY:
            existing = _REGISTRY[name]
            if existing is fn:
                return fn
            raise ValueError(
                f"check function {name!r} already registered "
                f"(existing: {existing.__module__}.{existing.__qualname__})"
            )
        _REGISTRY[name] = fn
        return fn

    return decorator


def get_check(name: str) -> CheckFn:
    """Look up a registered check function by name. Raises KeyError if missing."""
    if name not in _REGISTRY:
        raise KeyError(
            f"no check function registered for {name!r}; "
            f"known checks: {sorted(_REGISTRY)!r}"
        )
    return _REGISTRY[name]


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def _import_all_checks() -> None:
    """Import every check module so decorators run and the registry is populated.

    Called once at rubric load time. Adding a new check category means adding
    one import here.
    """
    # Local imports keep registry import-cycle-safe.
    from sdr_grader.rules.checks import (  # noqa: F401
        attribution,
        calc_metrics,
        governance,
        naming,
        platform_specific,
        schema_hygiene,
        segments,
    )

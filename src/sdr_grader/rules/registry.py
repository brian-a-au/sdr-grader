"""Check function registry.

Per SPEC §6: rules are YAML; checks are pure Python functions registered by
name via the @register_check decorator. The registry is a global dict;
rubric loading looks up each rule's `check:` field here. This is a function
lookup with a declared param contract, not a plugin system — keep it simple.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sdr_grader.rules.params import ParamSpec

if TYPE_CHECKING:
    from sdr_grader.core.models import Implementation
    from sdr_grader.render import Finding
    from sdr_grader.rules.engine import RuleContext

CheckFn = Callable[["Implementation", "RuleContext"], list["Finding"]]


@dataclass(frozen=True)
class CheckContract:
    """The params a check reads; the rubric loader validates YAML against it."""

    params: Mapping[str, ParamSpec] = field(default_factory=dict)
    alias_groups: tuple[tuple[str, ...], ...] = ()


_REGISTRY: dict[str, CheckFn] = {}
_CONTRACTS: dict[str, CheckContract] = {}


def register_check(
    name: str,
    *,
    params: Mapping[str, ParamSpec] | None = None,
    alias_groups: Iterable[tuple[str, ...]] = (),
) -> Callable[[CheckFn], CheckFn]:
    """Register a check function and the params it reads under the given name.

    Raises if the name is already registered to keep packs unambiguous.
    """
    contract = CheckContract(dict(params or {}), tuple(tuple(g) for g in alias_groups))
    for group in contract.alias_groups:
        if not set(group) <= set(contract.params):
            raise ValueError(f"check {name!r}: alias group {group!r} names undeclared params")

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
        _CONTRACTS[name] = contract
        return fn

    return decorator


def get_check(name: str) -> CheckFn:
    """Look up a registered check function by name. Raises KeyError if missing."""
    if name not in _REGISTRY:
        raise KeyError(
            f"no check function registered for {name!r}; known checks: {sorted(_REGISTRY)!r}"
        )
    return _REGISTRY[name]


def get_contract(name: str) -> CheckContract:
    """Look up a registered check's param contract. Raises KeyError if missing."""
    get_check(name)
    return _CONTRACTS[name]


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def _import_all_checks() -> None:
    """Import every check module so decorators run and the registry is populated.

    Called once at rubric load time. Adding a new check category means adding
    one import here.
    """
    # Local imports keep registry import-cycle-safe.
    from sdr_grader.rules.checks import (  # noqa: F401
        aa_admin,
        attribution,
        calc_metrics,
        governance,
        naming,
        schema_hygiene,
        segments,
        supplementary,
    )

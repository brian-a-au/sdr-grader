"""Property-based fuzz tests for the AA + CJA adapters.

The contract: any input that isn't a valid snapshot must raise
InvalidSnapshotError. The adapter is never allowed to crash with
TypeError, KeyError, AttributeError, or any other unexpected exception
type — that would indicate a missing guard the user can't usefully
recover from.

Two strategies are used:

1. Random top-level shapes (mostly catches bare-input bugs — None,
   wrong type at root, missing keys).
2. Mutations of a known-good fixture (deletes keys, swaps types, injects
   nulls deep in the tree) — catches the more interesting "we tolerate
   the happy path but not the realistic edge" bugs.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sdr_grader.adapters import aa as aa_adapter
from sdr_grader.adapters import cja as cja_adapter
from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.models import Implementation

FIXTURES = Path(__file__).parent / "fixtures"

ALLOWED_EXCEPTIONS = (InvalidSnapshotError,)


def _scalars() -> st.SearchStrategy[Any]:
    return st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**31), max_value=2**31),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
        st.text(max_size=40),
    )


def _json_values() -> st.SearchStrategy[Any]:
    return st.recursive(
        _scalars(),
        lambda children: st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(st.text(max_size=10), children, max_size=4),
        ),
        max_leaves=8,
    )


@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200, deadline=None)
@given(payload=_json_values())
@pytest.mark.parametrize("adapter", [aa_adapter, cja_adapter])
def test_adapter_never_crashes_on_random_input(adapter, payload):
    """No matter what JSON we feed in, the adapter raises InvalidSnapshotError
    or returns an Implementation — nothing else."""
    try:
        result = adapter.adapt(payload, source="<fuzz>")
    except ALLOWED_EXCEPTIONS:
        return  # expected path
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"{adapter.__name__} raised {type(exc).__name__} on random input — "
            "should be InvalidSnapshotError or success"
        ) from exc
    assert isinstance(result, Implementation)


# ---------------------------------------------------------------------------
# Mutation fuzz: start from a good fixture, perturb, ensure we still fail
# gracefully or succeed.
# ---------------------------------------------------------------------------


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _all_paths(node: Any, prefix: tuple = ()) -> list[tuple]:
    out: list[tuple] = []
    if isinstance(node, dict):
        for k, v in node.items():
            out.append(prefix + (k,))
            out.extend(_all_paths(v, prefix + (k,)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.append(prefix + (i,))
            out.extend(_all_paths(v, prefix + (i,)))
    return out


def _set_at(root: Any, path: tuple, value: Any) -> None:
    cur = root
    for step in path[:-1]:
        cur = cur[step]
    cur[path[-1]] = value


def _delete_at(root: Any, path: tuple) -> None:
    cur = root
    for step in path[:-1]:
        cur = cur[step]
    if isinstance(cur, dict):
        cur.pop(path[-1], None)
    elif isinstance(cur, list):
        import contextlib

        with contextlib.suppress(IndexError):
            cur.pop(path[-1])


@pytest.mark.parametrize(
    ("fixture_name", "adapter"),
    [
        ("aa_snapshot_clean.json", aa_adapter),
        ("aa_snapshot_messy.json", aa_adapter),
        ("cja_snapshot_clean.json", cja_adapter),
        ("cja_snapshot_messy.json", cja_adapter),
    ],
)
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(seed=st.integers(min_value=0, max_value=2**32 - 1),
       mutation=st.sampled_from([
           "delete", "replace_none", "replace_int", "replace_str",
           "replace_truthy_int", "replace_json_list_string",
       ]))
def test_adapter_survives_mutated_fixture(fixture_name, adapter, seed, mutation):
    """Take a valid fixture, mutate one path, confirm graceful handling."""
    import random

    rng = random.Random(seed)
    doc = copy.deepcopy(_load(fixture_name))
    paths = _all_paths(doc)
    if not paths:
        return
    target = rng.choice(paths)

    if mutation == "delete":
        _delete_at(doc, target)
    elif mutation == "replace_none":
        _set_at(doc, target, None)
    elif mutation == "replace_int":
        _set_at(doc, target, 0)
    elif mutation == "replace_str":
        _set_at(doc, target, "")
    elif mutation == "replace_truthy_int":
        _set_at(doc, target, 7)
    elif mutation == "replace_json_list_string":
        _set_at(doc, target, '["fuzzed"]')

    try:
        result = adapter.adapt(doc, source=f"<mutation:{mutation}:{target}>")
    except ALLOWED_EXCEPTIONS:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"{adapter.__name__} crashed with {type(exc).__name__} after mutating "
            f"path={target} via {mutation}: {exc}"
        ) from exc
    assert isinstance(result, Implementation)

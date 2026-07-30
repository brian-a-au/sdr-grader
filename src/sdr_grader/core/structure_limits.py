"""Iterative structure budgets for untrusted snapshot and definition JSON."""

from __future__ import annotations

from typing import Any

from sdr_grader.core.exceptions import InvalidSnapshotError

MAX_STRUCTURE_DEPTH = 100
MAX_STRUCTURE_NODES = 250_000
MAX_DEFINITION_NODES = 10_000


def measure_structure(value: Any) -> tuple[int, int]:
    """Return ``(node_count, maximum_depth)`` without recursive Python calls."""
    nodes = 0
    maximum_depth = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        maximum_depth = max(maximum_depth, depth)
        if isinstance(node, dict):
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
    return nodes, maximum_depth


def validate_snapshot_structure(value: Any, *, label: str) -> None:
    """Reject a snapshot that exceeds the public input structure budget."""
    _validate_structure(
        value,
        label=label,
        max_depth=MAX_STRUCTURE_DEPTH,
        max_nodes=MAX_STRUCTURE_NODES,
    )


def validate_definition_structure(value: Any, *, label: str) -> None:
    """Reject one decoded formula/segment definition outside its tighter budget."""
    _validate_structure(
        value,
        label=label,
        max_depth=MAX_STRUCTURE_DEPTH,
        max_nodes=MAX_DEFINITION_NODES,
    )


def validate_unicode_scalars(value: Any, *, label: str) -> None:
    """Reject surrogate code points in JSON-like string values and mapping keys.

    This walk intentionally adds no size or depth budget. It is used for
    embedded JSON that has already passed the outer snapshot budget.
    """
    stack = [value]
    while stack:
        node = stack.pop()
        _validate_string(node, label=label)
        if isinstance(node, dict):
            for key in node:
                _validate_string(key, label=label)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def _validate_string(value: Any, *, label: str) -> None:
    if isinstance(value, str) and any(
        0xD800 <= ord(character) <= 0xDFFF for character in value
    ):
        raise InvalidSnapshotError(f"{label} contains a Unicode surrogate code point")


def _validate_structure(
    value: Any,
    *,
    label: str,
    max_depth: int,
    max_nodes: int,
) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        _validate_string(node, label=label)
        if isinstance(node, dict):
            for key in node:
                _validate_string(key, label=label)
        if depth > max_depth:
            raise InvalidSnapshotError(
                f"{label} exceeds the maximum structure depth of {max_depth}"
            )
        nodes += 1
        if nodes > max_nodes:
            raise InvalidSnapshotError(f"{label} exceeds the maximum of {max_nodes:,} nodes")
        if isinstance(node, dict):
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)

"""Exact boundary tests for hostile JSON structure budgets."""

from __future__ import annotations

import pytest

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.structure_limits import (
    MAX_DEFINITION_NODES,
    MAX_STRUCTURE_DEPTH,
    MAX_STRUCTURE_NODES,
    measure_structure,
    validate_definition_structure,
    validate_snapshot_structure,
)


def _nested(depth: int):
    node = 0
    for _ in range(depth):
        node = {"child": node}
    return node


def test_measure_structure_counts_mixed_containers_iteratively():
    value = {
        "items": [
            1,
            {"nested": [2, 3]},
        ]
    }

    assert measure_structure(value) == (7, 4)


def test_snapshot_depth_boundary_accepts_100_and_rejects_101():
    validate_snapshot_structure(_nested(MAX_STRUCTURE_DEPTH), label="test snapshot")

    with pytest.raises(InvalidSnapshotError, match=r"test snapshot.*depth.*100"):
        validate_snapshot_structure(_nested(MAX_STRUCTURE_DEPTH + 1), label="test snapshot")


def test_snapshot_node_boundary_accepts_250000_and_rejects_next():
    validate_snapshot_structure([0] * (MAX_STRUCTURE_NODES - 1), label="test snapshot")

    with pytest.raises(InvalidSnapshotError, match=r"test snapshot.*250,000 nodes"):
        validate_snapshot_structure([0] * MAX_STRUCTURE_NODES, label="test snapshot")


def test_definition_node_boundary_accepts_10000_and_rejects_next():
    validate_definition_structure([0] * (MAX_DEFINITION_NODES - 1), label="test definition")

    with pytest.raises(InvalidSnapshotError, match=r"test definition.*10,000 nodes"):
        validate_definition_structure([0] * MAX_DEFINITION_NODES, label="test definition")

"""Deterministic SCC cycle detection (spec F3/F10)."""

from __future__ import annotations

from sdr_grader.rules.checks._helpers import cycle_groups


def test_finds_the_cycle_the_old_dfs_missed():
    # Old visited-set DFS reported only one of the two cycles here.
    graph = {"a": ["b", "c"], "b": ["a"], "c": ["b"]}
    assert cycle_groups(graph) == [["a", "b", "c"]]


def test_disjoint_cycles_and_self_loop_sorted():
    graph = {"m": ["n"], "n": ["m"], "x": ["x"], "y": ["m"]}
    assert cycle_groups(graph) == [["m", "n"], ["x"]]


def test_acyclic_graph_returns_empty():
    graph = {"a": ["b"], "b": ["c"], "c": []}
    assert cycle_groups(graph) == []


def test_edges_to_unknown_nodes_are_ignored():
    graph = {"a": ["ghost"], "b": ["a"]}
    assert cycle_groups(graph) == []


def test_deep_chain_does_not_hit_recursion_limit():
    graph = {f"n{i:05d}": [f"n{i + 1:05d}"] for i in range(3000)}
    graph["n03000"] = []
    assert cycle_groups(graph) == []


def test_output_is_stable_across_calls_and_input_order():
    forward = {"a": ["b"], "b": ["a"], "c": ["d"], "d": ["c"]}
    backward = {"d": ["c"], "c": ["d"], "b": ["a"], "a": ["b"]}
    assert cycle_groups(forward) == cycle_groups(backward) == [["a", "b"], ["c", "d"]]

"""Shared builders for direct-call rule tests.

The rule modules are pure functions; tests construct an Implementation
in-memory and call the check function directly. These helpers keep the
boilerplate out of each test file.
"""

from __future__ import annotations

from typing import Any

from sdr_grader.core.models import (
    CalculatedMetric,
    Component,
    Implementation,
    Segment,
)
from sdr_grader.rules.engine import RuleContext


def component(idx: int, *, comp_type: str = "metric", name: str | None = None,
              cid: str | None = None, description: str | None = "ok",
              data_type: str = "integer", tags: list[str] | None = None,
              owner: str | None = "owner") -> Component:
    return Component(
        id=cid or f"metrics/m_{idx:03d}",
        name=name or f"Component {idx:03d}",
        description=description,
        component_type=comp_type,  # type: ignore[arg-type]
        data_type=data_type,
        polarity=None,
        created_at=None,
        modified_at=None,
        owner=owner,
        tags=tags or [],
    )


def segment(sid: str, *, references: list[str] | None = None,
            container_types: list[str] | None = None, nesting_depth: int = 1,
            description: str | None = "ok", definition: dict | None = None,
            approved: bool | None = None,
            shared_to_count: int | None = None) -> Segment:
    return Segment(
        id=sid,
        name=sid,
        description=description,
        definition=definition or {},
        nesting_depth=nesting_depth,
        container_types=container_types or ["event"],
        references=references or [],
        approved=approved,
        shared_to_count=shared_to_count,
    )


def calc(cid: str, *, references: list[str] | None = None,
         attribution_model: str | None = None, allocation: str | None = None,
         description: str | None = "ok", complexity_score: float = 10.0,
         formula_text: str = "x / y", name: str | None = None,
         approved: bool | None = None,
         shared_to_count: int | None = None) -> CalculatedMetric:
    return CalculatedMetric(
        id=cid,
        name=name or cid,
        description=description,
        formula={},
        formula_text=formula_text,
        attribution_model=attribution_model,
        allocation=allocation,
        complexity_score=complexity_score,
        references=references or [],
        approved=approved,
        shared_to_count=shared_to_count,
    )


def impl(*, platform: str = "cja", metrics=None, dimensions=None,
         derived=None, segments=None, calc=None, raw=None) -> Implementation:
    return Implementation(
        platform=platform,  # type: ignore[arg-type]
        instance_id="dv_test",
        instance_name="Test",
        snapshot_taken_at=None,
        snapshot_source="test",
        adapter_version="0",
        metrics=metrics or [],
        dimensions=dimensions or [],
        segments=segments or [],
        calculated_metrics=calc or [],
        derived_fields=derived or [],
        raw=raw if raw is not None else {},
    )


def ctx(rule_id: str, severity: str = "medium", category: str = "schema_hygiene",
        platforms: list[str] | None = None, **params: Any) -> RuleContext:
    return RuleContext(
        rule_id=rule_id,
        rule_name=rule_id,
        severity=severity,
        category=category,
        platforms=platforms or ["cja", "aa"],
        params=params,
        rationale="rationale.",
        remediation="how to fix.",
    )

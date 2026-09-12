"""Pure inventory comparison and narrow grading eligibility for references.

Exclusions retain unresolved status. They never augment inventory or rewrite
canonical references, which remain available to every other check.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from sdr_grader.core.models import Implementation

POLICY_PARAM = "exclude_unresolved_calculated_metric_segments"
REFERENCE_CHECKS = frozenset({"broken_references", "calc_formula_broken_refs"})


class ReferenceCandidate(NamedTuple):
    consumer_kind: str
    consumer_id: str
    target_id: str


@dataclass(frozen=True)
class ReferenceAssessment:
    resolved: tuple[ReferenceCandidate, ...]
    unresolved_scoring: tuple[ReferenceCandidate, ...]
    excluded: tuple[ReferenceCandidate, ...]

    @property
    def not_assessed(self) -> bool:
        """Only an excluded-only population changes existing applicability."""
        return bool(self.excluded) and not (self.resolved or self.unresolved_scoring)


def assess_references(
    impl: Implementation, *, check_name: str, params: Mapping[str, Any]
) -> ReferenceAssessment:
    """Partition canonical candidates, preserving order and duplicate occurrences.

    Known IDs deliberately use the existing untyped inventory union. The policy
    applies afterward, only with an explicit boolean opt-in and unambiguous
    normalized segment typing on a uniquely identified calculated metric.
    """
    if check_name not in REFERENCE_CHECKS:
        raise ValueError(f"unsupported reference check: {check_name!r}")
    known = {
        item.id
        for collection in (
            impl.metrics,
            impl.dimensions,
            impl.derived_fields,
            impl.segments,
            impl.calculated_metrics,
        )
        for item in collection
    } | impl.available_reference_ids
    consumer_counts = Counter(cm.id for cm in impl.calculated_metrics)
    enabled = params.get(POLICY_PARAM) is True
    resolved: list[ReferenceCandidate] = []
    scoring: list[ReferenceCandidate] = []
    excluded: list[ReferenceCandidate] = []

    if check_name == "broken_references":
        for segment in impl.segments:
            for ref in segment.references:
                candidate = ReferenceCandidate("segment", segment.id, ref)
                (resolved if ref in known else scoring).append(candidate)
    for cm in impl.calculated_metrics:
        for ref in cm.references:
            candidate = ReferenceCandidate("calc_metric", cm.id, ref)
            if ref in known:
                resolved.append(candidate)
                continue
            classification = cm.reference_classifications.get(ref)
            if (
                enabled
                and consumer_counts[cm.id] == 1
                and classification is not None
                and classification.kinds == frozenset({"segment"})
                and not classification.blockers
            ):
                excluded.append(candidate)
            else:
                scoring.append(candidate)
    return ReferenceAssessment(tuple(resolved), tuple(scoring), tuple(excluded))

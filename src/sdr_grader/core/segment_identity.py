"""Require one consistent normalized Segment record per inventory identity."""

from __future__ import annotations

from dataclasses import replace

from sdr_grader.core.exceptions import InvalidSnapshotError
from sdr_grader.core.models import Implementation, Segment


def validate_segment_identities(impl: Implementation) -> None:
    """Reject conflicting duplicate IDs without deduplicating inventory rows.

    Compare the complete normalized record, treating references as an unordered
    set of graph edges. Canonicalization is comparison-only: supplied records,
    reference lists, and inventory counts remain intact. Other inventory kinds
    have independent namespaces and may legitimately reuse a segment ID.
    """
    seen: dict[str, tuple[int, Segment]] = {}
    for index, segment in enumerate(impl.segments):
        canonical = replace(segment, references=sorted(set(segment.references)))
        previous = seen.get(segment.id)
        if previous is not None:
            first_index, first_record = previous
            if canonical != first_record:
                raise InvalidSnapshotError(
                    f"{impl.snapshot_source}: segments[{index}] conflicts with "
                    f"segments[{first_index}] for the same normalized segment ID"
                )
        else:
            seen[segment.id] = (index, canonical)

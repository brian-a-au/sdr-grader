"""Auto-detect platform from a parsed JSON snapshot's top-level shape.

Per SPEC §5: CJA snapshots have a `metadata` object with "Data View ID" and
top-level `metrics` / `dimensions` arrays. AA snapshots have `report_suite`
with rsid plus top-level `metrics` / `dimensions` / (often) classifications.
"""

from __future__ import annotations

from typing import Any

from sdr_grader.core.exceptions import UnknownPlatformError


def detect_platform(snapshot: Any) -> str:
    """Return 'cja' or 'aa'. Raise UnknownPlatformError on ambiguous shape."""
    if not isinstance(snapshot, dict):
        raise UnknownPlatformError(
            "snapshot is not a JSON object; cannot auto-detect platform"
        )
    metadata = snapshot.get("metadata")
    if isinstance(metadata, dict) and any(
        k in metadata for k in ("Data View ID", "data_view_id", "dataViewId")
    ):
        return "cja"
    rs = snapshot.get("report_suite") or snapshot.get("reportSuite")
    if isinstance(rs, dict) and (rs.get("rsid") or rs.get("RSID")):
        return "aa"
    if "data_view" in snapshot or "dataView" in snapshot:
        return "cja"
    raise UnknownPlatformError(
        "could not auto-detect platform from snapshot shape; "
        "pass --platform cja|aa to override"
    )

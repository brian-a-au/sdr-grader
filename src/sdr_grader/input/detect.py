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
    looks_cja = isinstance(metadata, dict) and any(
        k in metadata for k in ("Data View ID", "data_view_id", "dataViewId")
    )
    rs = snapshot.get("report_suite") or snapshot.get("reportSuite")
    looks_aa = isinstance(rs, dict) and bool(rs.get("rsid") or rs.get("RSID"))
    if looks_cja and looks_aa:
        raise UnknownPlatformError(
            "snapshot matches both CJA and AA shapes; "
            "pass --platform cja|aa to disambiguate"
        )
    if looks_cja:
        return "cja"
    if looks_aa:
        return "aa"
    raise UnknownPlatformError(
        "could not auto-detect platform from snapshot shape; "
        "pass --platform cja|aa to override"
    )

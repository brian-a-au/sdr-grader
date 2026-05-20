"""Sanitize a raw SDR snapshot for inclusion in the calibration corpus.

The grader's calibration corpus needs real production SDRs to set
defensible thresholds, but those snapshots carry tenant-identifying
fields (report-suite IDs, data-view IDs, owner emails, report-suite
names). This script rewrites those fields deterministically so the same
input always yields the same anonymized output (determinism contract
applies to the corpus too).

What this DOES touch:
    - report_suite.rsid / report_suite.name / report_suite.parent_rsid (AA)
    - data_view.data_view_id / data_view.data_view_name and the matching
      metadata entries (CJA)
    - owner emails on components
    - any field name supplied via --redact-field

What this does NOT touch:
    - component descriptions, dimension/metric/segment names beyond the
      report-suite or data-view labels themselves. The grader scores
      description presence and quality, so stripping them would
      invalidate the calibration. The submitter is responsible for
      reviewing descriptions for embedded PII before adding the file
      to the corpus.

Usage:
    uv run python scripts/sanitize_sdr.py INPUT.json \\
        --platform {cja,aa} \\
        --output tests/fixtures/private/{platform}/{anon-id}.json \\
        [--redact word,word,...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def _anon_token(value: str, *, prefix: str, length: int = 8) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def _anon_email(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"owner-{digest}@anon.example"


def _redact_words(text: str, patterns: list[re.Pattern[str]]) -> str:
    out = text
    for pat in patterns:
        out = pat.sub("[redacted]", out)
    return out


def _walk_redact(node: Any, patterns: list[re.Pattern[str]]) -> Any:
    if isinstance(node, str):
        return _redact_words(node, patterns)
    if isinstance(node, list):
        return [_walk_redact(item, patterns) for item in node]
    if isinstance(node, dict):
        return {k: _walk_redact(v, patterns) for k, v in node.items()}
    return node


def sanitize_aa(doc: dict[str, Any]) -> dict[str, Any]:
    rs = doc.get("report_suite") or {}
    rsid = rs.get("rsid")
    if rsid:
        rs["rsid"] = _anon_token(rsid, prefix="rsid")
    if rs.get("name"):
        rs["name"] = _anon_token(rs["name"], prefix="rs-name")
    if rs.get("parent_rsid"):
        rs["parent_rsid"] = _anon_token(rs["parent_rsid"], prefix="rsid")
    doc["report_suite"] = rs
    return doc


def sanitize_cja(doc: dict[str, Any]) -> dict[str, Any]:
    dv = doc.get("data_view") or {}
    dv_id = dv.get("data_view_id")
    if dv_id:
        dv["data_view_id"] = _anon_token(dv_id, prefix="dv")
    if dv.get("data_view_name"):
        dv["data_view_name"] = _anon_token(dv["data_view_name"], prefix="dv-name")
    doc["data_view"] = dv

    meta = doc.get("metadata") or {}
    if "Data View ID" in meta:
        meta["Data View ID"] = _anon_token(meta["Data View ID"], prefix="dv")
    if "Data View Name" in meta:
        meta["Data View Name"] = _anon_token(meta["Data View Name"], prefix="dv-name")
    doc["metadata"] = meta

    _scrub_owner_emails_cja(doc)
    return doc


def _scrub_owner_emails_cja(doc: dict[str, Any]) -> None:
    flat = ("metrics", "dimensions")
    for collection in flat:
        for item in doc.get(collection) or []:
            owner = item.get("owner") if isinstance(item, dict) else None
            if isinstance(owner, str) and "@" in owner:
                item["owner"] = _anon_email(owner)

    # CJA wraps segments / calculated_metrics in {summary, segments|metrics}.
    for wrapper, inner_key in (("segments", "segments"), ("calculated_metrics", "metrics")):
        container = doc.get(wrapper)
        if not isinstance(container, dict):
            continue
        for item in container.get(inner_key) or []:
            if not isinstance(item, dict):
                continue
            owner = item.get("owner")
            if isinstance(owner, str) and "@" in owner:
                item["owner"] = _anon_email(owner)


def sanitize(doc: dict[str, Any], *, platform: str,
             redact_patterns: list[re.Pattern[str]]) -> dict[str, Any]:
    if platform == "aa":
        doc = sanitize_aa(doc)
    elif platform == "cja":
        doc = sanitize_cja(doc)
    else:
        raise ValueError(f"unsupported platform: {platform}")

    if redact_patterns:
        doc = _walk_redact(doc, redact_patterns)
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw SDR JSON to sanitize")
    parser.add_argument("--platform", choices=("cja", "aa"), required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="destination for sanitized JSON")
    parser.add_argument("--redact", default="",
                        help="comma-separated case-insensitive words to scrub everywhere")
    args = parser.parse_args(argv)

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    patterns = [
        re.compile(re.escape(w.strip()), re.IGNORECASE)
        for w in args.redact.split(",") if w.strip()
    ]
    cleaned = sanitize(raw, platform=args.platform, redact_patterns=patterns)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(cleaned, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    anon_id = _anon_token(str(args.input.resolve()), prefix="sdr", length=10)
    print(f"sanitized -> {args.output}")
    print(f"suggested manifest anon_id: {anon_id}")
    print("REMINDER: review component descriptions for embedded PII before adding to corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

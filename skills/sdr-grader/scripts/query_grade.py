#!/usr/bin/env python3
"""Query helper for sdr-grader --json output.

Subcommands:
    summary FILE                          One-line grade + per-category roll-up.
    findings FILE [filters]               List findings, optionally filtered.
    show FILE RULE_ID                     Pretty-print one finding's body.
    compare FILE OTHER                    Diff two grade JSONs.

The script intentionally has no third-party dependencies so it runs from
the bundled skill folder without any setup.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="query_grade")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_summary = sub.add_parser("summary", help="One-line grade + categories")
    p_summary.add_argument("path")

    p_findings = sub.add_parser("findings", help="List findings (filterable)")
    p_findings.add_argument("path")
    p_findings.add_argument("--severity", choices=["critical", "high", "medium", "low"])
    p_findings.add_argument("--category", help="Match against finding.category (case-insensitive substring).")
    p_findings.add_argument("--rule", help="Match against finding.id (prefix or exact).")

    p_show = sub.add_parser("show", help="Print one finding's body + remediation")
    p_show.add_argument("path")
    p_show.add_argument("rule")

    p_compare = sub.add_parser("compare", help="Diff two grade JSONs")
    p_compare.add_argument("path")
    p_compare.add_argument("other")

    args = parser.parse_args(argv)

    try:
        report = _load(args.path)
    except _LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.cmd == "summary":
        return _summary(report)
    if args.cmd == "findings":
        return _findings(report, severity=args.severity, category=args.category, rule=args.rule)
    if args.cmd == "show":
        return _show(report, args.rule)
    if args.cmd == "compare":
        try:
            other = _load(args.other)
        except _LoadError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return _compare(report, other)
    return 1


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _summary(report: dict[str, Any]) -> int:
    print(
        f"{report.get('grade', '?')} ({report.get('overall_pct', 0)}%) — "
        f"{report.get('instance_name', '?')} via "
        f"{report.get('rubric', {}).get('pack', '?')}@{report.get('rubric', {}).get('version', '?')}"
    )
    print(f"  {len(report.get('findings', []))} findings, "
          f"{len(report.get('remediations', []))} remediations")
    for cat in report.get("categories", []):
        print(f"  · {cat['name']:<28} {cat['pct']:>3}%  {cat['grade']}")
    skipped = (report.get("methodology") or {}).get("skipped") or []
    if skipped:
        print(f"  Skipped rules ({sum(len(s.get('ids') or []) for s in skipped)}):")
        for entry in skipped:
            ids = ", ".join(entry.get("ids") or [])
            print(f"    - {ids}: {entry.get('reason', '')}")
    return 0


def _findings(report: dict[str, Any], *,
              severity: str | None, category: str | None, rule: str | None) -> int:
    findings = report.get("findings") or []
    if severity:
        findings = [f for f in findings if f.get("severity") == severity]
    if category:
        target = category.lower()
        findings = [
            f for f in findings
            if target in (f.get("category") or "").lower()
        ]
    if rule:
        findings = [
            f for f in findings
            if (f.get("id") or "").startswith(rule) or f.get("id") == rule
        ]

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.get("severity", "low"), 99),
                                 f.get("id", "")))
    if not findings:
        print("(no findings match filters)")
        return 0
    for f in findings:
        print(f"  [{f.get('severity', '?'):<8}] {f.get('id', '?'):<14} "
              f"{f.get('title', '')}")
    return 0


def _show(report: dict[str, Any], rule_id: str) -> int:
    findings = report.get("findings") or []
    finding = next((f for f in findings if f.get("id") == rule_id), None)
    if not finding:
        print(f"no finding with id {rule_id!r} in this grade JSON")
        return 1
    print(f"{finding['id']} — {finding.get('severity', '?')} — {finding.get('category', '?')}")
    print(finding.get("title", ""))
    print()
    for block in finding.get("body") or []:
        kind = block.get("kind")
        if kind == "paragraph":
            print(_strip_inline_html(block.get("html") or ""))
            print()
        elif kind == "section":
            label = block.get("label", "")
            body = _strip_inline_html(block.get("body_html") or "")
            print(f"## {label}")
            if body:
                print(body)
            print()
        elif kind == "components":
            for item in block.get("items") or []:
                print(f"  - {item}")
            print()
        elif kind == "code":
            print("```")
            print(block.get("text", ""))
            print("```")
            print()

    matching_remediations = [
        r for r in report.get("remediations") or []
        if rule_id in (r.get("refs") or [])
    ]
    if matching_remediations:
        print("Remediations:")
        for r in matching_remediations:
            print(f"  · {r.get('text', '')} (impact: {r.get('impact_pts', 0)} pts)")
    return 0


def _compare(report: dict[str, Any], other: dict[str, Any]) -> int:
    label_a = f"{report.get('grade', '?')} ({report.get('overall_pct', 0)}%)"
    label_b = f"{other.get('grade', '?')} ({other.get('overall_pct', 0)}%)"
    delta = (report.get("overall_pct") or 0) - (other.get("overall_pct") or 0)
    sign = "+" if delta > 0 else ""
    print(f"{report.get('id', 'A')}: {label_a}")
    print(f"{other.get('id', 'B')}: {label_b}")
    print(f"Delta: {sign}{delta} pts")
    print()

    a_ids = {f.get("id") for f in report.get("findings") or []}
    b_ids = {f.get("id") for f in other.get("findings") or []}
    appeared = sorted(a_ids - b_ids)
    resolved = sorted(b_ids - a_ids)
    common = sorted(a_ids & b_ids)
    print(f"Appeared since other: {len(appeared)}")
    for fid in appeared:
        print(f"  + {fid}")
    print(f"Resolved since other: {len(resolved)}")
    for fid in resolved:
        print(f"  - {fid}")
    print(f"Common findings: {len(common)}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _LoadError(Exception):
    pass


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise _LoadError(f"file not found: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _LoadError(f"{path}: not valid JSON: {exc}") from exc


def _strip_inline_html(html: str) -> str:
    """Crude tag stripper for terminal output. The grader emits restricted
    inline HTML; this is good enough to read in a shell."""
    out = []
    in_tag = False
    for ch in html:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            out.append(ch)
    return (
        "".join(out)
        .replace("&ldquo;", "“")
        .replace("&rdquo;", "”")
        .replace("&rsquo;", "’")
        .replace("&ge;", "≥")
        .replace("&le;", "≤")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only queries over bounded, validated sdr-grader JSON reports."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_COLLECTION_ITEMS = 100_000
MAX_STRING_CHARS = 1 * 1024 * 1024
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
LEGACY_WARNING = (
    "warning: legacy report has no stable schema/instance identity; "
    "this single-report read is non-comparative"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="query_grade",
        allow_abbrev=False,
    )
    subcommands = parser.add_subparsers(dest="cmd", required=True)

    summary = subcommands.add_parser(
        "summary",
        help="One-line grade + categories",
        allow_abbrev=False,
    )
    summary.add_argument("path")

    findings = subcommands.add_parser(
        "findings",
        help="List findings (filterable)",
        allow_abbrev=False,
    )
    findings.add_argument("path")
    findings.add_argument(
        "--severity",
        choices=["critical", "high", "medium", "low"],
    )
    findings.add_argument(
        "--category",
        help="Match finding.category (case-insensitive; spaces and underscores agree).",
    )
    findings.add_argument(
        "--rule",
        help="Match finding.id by prefix or exact value.",
    )

    show = subcommands.add_parser(
        "show",
        help="Print one finding's body + remediation",
        allow_abbrev=False,
    )
    show.add_argument("path")
    show.add_argument("rule")

    compare = subcommands.add_parser(
        "compare",
        help="Compare compatible grade JSONs",
        allow_abbrev=False,
    )
    compare.add_argument("path")
    compare.add_argument("other")

    args = parser.parse_args(argv)
    try:
        report = _load(args.path)
    except _LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.cmd == "compare":
        comparison_report = _comparison_projection(report)
        del report
        try:
            other_report = _load(args.other)
        except _LoadError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        other_comparison = _comparison_projection(other_report)
        del other_report
        return _compare(comparison_report, other_comparison)

    if _is_legacy(report):
        print(LEGACY_WARNING, file=sys.stderr)
    if args.cmd == "summary":
        return _summary(report)
    if args.cmd == "findings":
        return _findings(
            report,
            severity=args.severity,
            category=args.category,
            rule=args.rule,
        )
    if args.cmd == "show":
        return _show(report, args.rule)
    return 1


def _summary(report: dict[str, Any]) -> int:
    rubric = report["rubric"]
    print(
        f"{report['grade']} ({report['overall_pct']}%) — "
        f"{report['instance_name']} via "
        f"{rubric['pack']}@{rubric['version']}"
    )
    print(
        f"  {len(report['findings'])} findings, "
        f"{len(report['remediations'])} remediations"
    )
    for category in report["categories"]:
        print(
            f"  · {category['name']:<28} "
            f"{category['pct']:>3}%  {category['grade']}"
        )
    skipped = report["methodology"].get("skipped") or []
    if skipped:
        count = sum(len(entry.get("ids") or []) for entry in skipped)
        print(f"  Skipped rules ({count}):")
        for entry in skipped:
            ids = ", ".join(entry.get("ids") or [])
            print(f"    - {ids}: {entry.get('reason', '')}")
    return 0


def _findings(
    report: dict[str, Any],
    *,
    severity: str | None,
    category: str | None,
    rule: str | None,
) -> int:
    matches = list(report["findings"])
    if severity:
        matches = [
            finding
            for finding in matches
            if finding["severity"] == severity
        ]
    if category:
        target = _normalized_category(category)
        matches = [
            finding
            for finding in matches
            if target in _normalized_category(finding["category"])
        ]
    if rule:
        matches = [
            finding
            for finding in matches
            if finding["id"].startswith(rule)
        ]

    matches.sort(
        key=lambda finding: (
            SEVERITY_ORDER[finding["severity"]],
            finding["id"],
        )
    )
    if not matches:
        print("(no findings match filters)")
        return 0
    for finding in matches:
        print(
            f"  [{finding['severity']:<8}] "
            f"{finding['id']:<14} {finding['title']}"
        )
    return 0


def _show(report: dict[str, Any], rule_id: str) -> int:
    finding = next(
        (
            candidate
            for candidate in report["findings"]
            if candidate["id"] == rule_id
        ),
        None,
    )
    if finding is None:
        print(f"no finding with id {rule_id!r} in this grade JSON")
        return 1
    print(
        f"{finding['id']} — {finding['severity']} — "
        f"{finding['category']}"
    )
    print(finding["title"])
    print()
    for block in finding["body"]:
        kind = block["kind"]
        if kind == "paragraph":
            print(_strip_inline_html(block.get("html") or ""))
            print()
        elif kind == "section":
            print(f"## {block.get('label') or ''}")
            body = _strip_inline_html(block.get("body_html") or "")
            if body:
                print(body)
            print()
        elif kind == "components":
            for item in block.get("items") or []:
                print(f"  - {item}")
            print()
        elif kind == "code":
            print("```")
            print(block.get("text") or "")
            print("```")
            print()

    matching = [
        remediation
        for remediation in report["remediations"]
        if rule_id in remediation["refs"]
    ]
    if matching:
        print("Remediations:")
        for remediation in matching:
            weight = remediation.get(
                "priority_weight",
                remediation.get("impact_pts", 0),
            )
            print(
                f"  · {remediation['text']} "
                f"(priority weight: {weight})"
            )
    return 0


def _compare(
    report: _ComparisonReport,
    other: _ComparisonReport,
) -> int:
    incompatibilities = _comparison_incompatibilities(report, other)
    if incompatibilities:
        print(
            "error: cannot compare authoritatively: "
            + "; ".join(incompatibilities),
            file=sys.stderr,
        )
        return 2

    warnings: list[str] = []
    if report.adapter_version != other.adapter_version:
        warnings.append("snapshot adapter versions differ")
    if report.tool_version != other.tool_version:
        warnings.append("sdr-grader versions differ")
    if warnings:
        print("warning: " + "; ".join(warnings), file=sys.stderr)

    label_a = f"{report.grade} ({report.overall_pct}%)"
    label_b = f"{other.grade} ({other.overall_pct}%)"
    delta = report.overall_pct - other.overall_pct
    sign = "+" if delta > 0 else ""
    print(f"{report.report_id}: {label_a}")
    print(f"{other.report_id}: {label_b}")
    print(f"Delta: {sign}{delta} percentage points")
    print()

    appeared = sorted(report.finding_ids - other.finding_ids)
    resolved = sorted(other.finding_ids - report.finding_ids)
    common = report.finding_ids & other.finding_ids
    print(f"Appeared since other: {len(appeared)}")
    for finding_id in appeared:
        print(f"  + {finding_id}")
    print(f"Resolved since other: {len(resolved)}")
    for finding_id in resolved:
        print(f"  - {finding_id}")
    print(f"Common findings: {len(common)}")
    return 0


def _comparison_incompatibilities(
    report: _ComparisonReport,
    other: _ComparisonReport,
) -> list[str]:
    if report.legacy or other.legacy:
        return ["legacy report lacks schema_version and stable instance identity"]

    comparisons = (
        ("schema version", report.schema_version, other.schema_version),
        ("instance ID", report.instance_id, other.instance_id),
        ("platform", report.platform, other.platform),
        ("adapter family", report.adapter_family, other.adapter_family),
        ("rubric pack", report.rubric_pack, other.rubric_pack),
        ("rubric version", report.rubric_version, other.rubric_version),
    )
    return [
        f"{label} differs ({left!r} vs {right!r})"
        for label, left, right in comparisons
        if left != right
    ]


@dataclass(frozen=True)
class _ComparisonReport:
    legacy: bool
    schema_version: int | None
    instance_id: str | None
    report_id: str
    grade: str
    overall_pct: int
    platform: str
    adapter_family: str
    adapter_version: str
    rubric_pack: str
    rubric_version: str
    tool_version: str
    finding_ids: frozenset[str]


def _comparison_projection(report: dict[str, Any]) -> _ComparisonReport:
    adapter = report["adapter"]
    rubric = report["rubric"]
    return _ComparisonReport(
        legacy=_is_legacy(report),
        schema_version=report.get("schema_version"),
        instance_id=report.get("instance_id"),
        report_id=report["id"],
        grade=report["grade"],
        overall_pct=report["overall_pct"],
        platform=adapter["platform"],
        adapter_family=adapter["tool"],
        adapter_version=adapter["version"],
        rubric_pack=rubric["pack"],
        rubric_version=rubric["version"],
        tool_version=report["tool_version"],
        finding_ids=frozenset(
            finding["id"] for finding in report["findings"]
        ),
    )


class _LoadError(Exception):
    """Safe, user-facing report-load failure."""


def _load(path: str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise _LoadError(f"file not found: {path}")
    try:
        with source.open("rb") as handle:
            payload = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        raise _LoadError(f"could not read report: {exc.strerror or 'I/O error'}") from exc
    if len(payload) > MAX_REPORT_BYTES:
        raise _LoadError(
            f"report is too large; maximum is {MAX_REPORT_BYTES} bytes"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _LoadError("report is not valid UTF-8") from exc
    del payload
    try:
        report = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_literal,
        )
    except json.JSONDecodeError as exc:
        raise _LoadError(
            f"report is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except RecursionError as exc:
        raise _LoadError("report exceeds the JSON decoder depth limit") from exc
    except ValueError as exc:
        raise _LoadError("report contains an invalid numeric value") from exc
    del text
    _validate_limits(report)
    _validate_report(report)
    return report


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _LoadError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_literal(value: str) -> Any:
    raise _LoadError(f"non-finite JSON value is not allowed: {value}")


def _validate_limits(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise _LoadError(f"report exceeds maximum JSON depth {MAX_JSON_DEPTH}")
    if isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            raise _LoadError("report contains an oversized string")
        if any(
            (ord(character) < 32 and character not in "\n\t")
            or ord(character) == 127
            for character in value
        ):
            raise _LoadError("report contains a terminal control character")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _LoadError("report contains a non-finite number")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise _LoadError("report contains an oversized list")
        for item in value:
            _validate_limits(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise _LoadError("report contains an oversized object")
        for key, item in value.items():
            _validate_limits(key, depth=depth + 1)
            _validate_limits(item, depth=depth + 1)
        return
    raise _LoadError(f"report contains unsupported value type {type(value).__name__}")


def _validate_report(report: Any) -> None:
    if not isinstance(report, dict):
        raise _LoadError("report root must be a JSON object")

    has_schema_version = "schema_version" in report
    has_instance_id = "instance_id" in report
    if has_schema_version != has_instance_id:
        raise _LoadError(
            "report must contain both schema_version and instance_id, or neither"
        )
    schema_version = report.get("schema_version")
    if has_schema_version and (
        type(schema_version) is not int
        or schema_version != REPORT_SCHEMA_VERSION
    ):
        raise _LoadError(
            f"unsupported report schema_version {schema_version!r}; "
            f"expected {REPORT_SCHEMA_VERSION}"
        )

    for key in ("id", "instance_name", "grade", "tool_version", "generated_at"):
        _require_string(report, key)
    if not _is_legacy(report):
        _require_string(report, "instance_id")
    _require_int(report, "overall_pct", minimum=0, maximum=100)

    adapter = _require_mapping(report, "adapter")
    for key in ("platform", "tool", "version"):
        _require_string(adapter, key, parent="adapter")
    rubric = _require_mapping(report, "rubric")
    for key in ("pack", "version"):
        _require_string(rubric, key, parent="rubric")

    categories = _require_list(report, "categories")
    for index, category in enumerate(categories):
        if not isinstance(category, dict):
            raise _LoadError(f"categories[{index}] must be an object")
        _require_string(category, "name", parent=f"categories[{index}]")
        _require_int(
            category,
            "pct",
            parent=f"categories[{index}]",
            minimum=0,
            maximum=100,
        )
        _require_string(category, "grade", parent=f"categories[{index}]")

    findings = _require_list(report, "findings")
    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        parent = f"findings[{index}]"
        if not isinstance(finding, dict):
            raise _LoadError(f"{parent} must be an object")
        finding_id = _require_string(finding, "id", parent=parent)
        if finding_id in seen_ids:
            raise _LoadError(f"duplicate finding ID: {finding_id}")
        seen_ids.add(finding_id)
        severity = _require_string(finding, "severity", parent=parent)
        if severity not in SEVERITY_ORDER:
            raise _LoadError(f"{parent}.severity is invalid")
        _require_string(finding, "category", parent=parent)
        _require_string(finding, "title", parent=parent, allow_empty=True)
        body = _require_list(finding, "body", parent=parent)
        for block_index, block in enumerate(body):
            block_parent = f"{parent}.body[{block_index}]"
            if not isinstance(block, dict):
                raise _LoadError(f"{block_parent} must be an object")
            kind = _require_string(block, "kind", parent=block_parent)
            if kind == "paragraph":
                _require_optional_string(block, "html", parent=block_parent)
            elif kind == "section":
                _require_optional_string(block, "label", parent=block_parent)
                _require_optional_string(
                    block,
                    "body_html",
                    parent=block_parent,
                )
            elif kind == "components":
                items = block.get("items")
                if items is not None and (
                    not isinstance(items, list)
                    or not all(isinstance(item, str) for item in items)
                ):
                    raise _LoadError(
                        f"{block_parent}.items must be null or a list of strings"
                    )
            elif kind == "code":
                _require_optional_string(block, "text", parent=block_parent)
            else:
                raise _LoadError(f"{block_parent}.kind is unsupported")

    remediations = _require_list(report, "remediations")
    for index, remediation in enumerate(remediations):
        parent = f"remediations[{index}]"
        if not isinstance(remediation, dict):
            raise _LoadError(f"{parent} must be an object")
        _require_string(remediation, "text", parent=parent, allow_empty=True)
        refs = _require_list(remediation, "refs", parent=parent)
        if not all(isinstance(ref, str) for ref in refs):
            raise _LoadError(f"{parent}.refs must contain only strings")
        if "priority_weight" in remediation:
            _require_int(remediation, "priority_weight", parent=parent)
        elif "impact_pts" in remediation:
            _require_int(remediation, "impact_pts", parent=parent)
        else:
            raise _LoadError(f"{parent} is missing priority weight")

    methodology = _require_mapping(report, "methodology")
    _require_list(methodology, "paragraphs", parent="methodology")
    skipped = _require_list(methodology, "skipped", parent="methodology")
    for index, entry in enumerate(skipped):
        if not isinstance(entry, dict):
            raise _LoadError(f"methodology.skipped[{index}] must be an object")
        ids = _require_list(
            entry,
            "ids",
            parent=f"methodology.skipped[{index}]",
        )
        if not all(isinstance(rule_id, str) for rule_id in ids):
            raise _LoadError(
                f"methodology.skipped[{index}].ids must contain strings"
            )
        _require_string(
            entry,
            "reason",
            parent=f"methodology.skipped[{index}]",
            allow_empty=True,
        )


def _require_mapping(
    value: dict[str, Any],
    key: str,
    *,
    parent: str = "report",
) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise _LoadError(f"{parent}.{key} must be an object")
    return result


def _require_list(
    value: dict[str, Any],
    key: str,
    *,
    parent: str = "report",
) -> list[Any]:
    result = value.get(key)
    if not isinstance(result, list):
        raise _LoadError(f"{parent}.{key} must be a list")
    return result


def _require_string(
    value: dict[str, Any],
    key: str,
    *,
    parent: str = "report",
    allow_empty: bool = False,
) -> str:
    result = value.get(key)
    if not isinstance(result, str) or (not allow_empty and not result):
        raise _LoadError(f"{parent}.{key} must be a non-empty string")
    return result


def _require_optional_string(
    value: dict[str, Any],
    key: str,
    *,
    parent: str,
) -> str | None:
    result = value.get(key)
    if result is not None and not isinstance(result, str):
        raise _LoadError(f"{parent}.{key} must be null or a string")
    return result


def _require_int(
    value: dict[str, Any],
    key: str,
    *,
    parent: str = "report",
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    result = value.get(key)
    if type(result) is not int:
        raise _LoadError(f"{parent}.{key} must be an integer")
    if minimum is not None and result < minimum:
        raise _LoadError(f"{parent}.{key} is below {minimum}")
    if maximum is not None and result > maximum:
        raise _LoadError(f"{parent}.{key} exceeds {maximum}")
    return result


def _is_legacy(report: dict[str, Any]) -> bool:
    return "schema_version" not in report and "instance_id" not in report


def _normalized_category(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _strip_inline_html(value: str) -> str:
    output: list[str] = []
    in_tag = False
    for character in value:
        if character == "<":
            in_tag = True
            continue
        if character == ">":
            in_tag = False
            continue
        if not in_tag:
            output.append(character)
    return html.unescape("".join(output)).strip()


if __name__ == "__main__":
    raise SystemExit(main())

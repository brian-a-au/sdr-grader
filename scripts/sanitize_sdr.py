"""Create a restricted review candidate from an AA or CJA snapshot.

This utility reduces disclosure risk before a production-derived snapshot
is reviewed. It does not decide that an artifact is safe to share. It
replaces recognized tenant identifiers, tenant names,
and owners throughout the JSON tree, then applies every value supplied via
``--redact`` to both keys and string values. Component descriptions remain
present because the grader evaluates them, so a human must review the full
candidate before sharing it.

Launch limits are deliberately conservative and public:

* input JSON: 16 MiB
* nesting depth: 64 containers
* one object or array: 100,000 entries
* one key or string: 1 MiB

Unsupported, ambiguous, non-finite, or over-limit content fails closed.
Successful output is staged beside the destination, installed atomically,
and restricted to the current user (mode 0600 where the platform supports
POSIX permissions).

Usage:
    uv run python scripts/sanitize_sdr.py INPUT.json \\
        --platform {cja,aa} \\
        --output restricted-review-candidate.json \\
        [--redact word,word,...]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64
MAX_COLLECTION_ITEMS = 100_000
MAX_STRING_LENGTH = 1024 * 1024

_REDACTED = "[redacted]"
_REDACTED_INT = -(2**63)
_REDACTED_FLOAT = -sys.float_info.max
_TOKEN_RE = re.compile(r"^(?:tid|tname|own)_[0-9a-f]{12}(?:@redacted\.invalid)?$")
_TENANT_ID_KEYS = {
    "dataviewid",
    "parentrsid",
    "reportsuiteid",
    "rsid",
}
_TENANT_NAME_KEYS = {"dataviewname", "reportsuitename"}
_OWNER_KEYS = {
    "createdby",
    "modifiedby",
    "owner",
    "owneremail",
    "ownerid",
}


class SanitizationError(ValueError):
    """A fail-closed sanitizer error with a stable, non-sensitive category."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class _SensitiveValue:
    original: str
    replacement: Any
    global_replace: bool


@dataclass(frozen=True)
class _ReplacementPlan:
    exact: dict[str, str]
    pattern: re.Pattern[str] | None


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _stable_token(value: Any, *, prefix: str) -> str:
    text = str(value)
    if _TOKEN_RE.fullmatch(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    label = {
        "tenant-id": "tid",
        "tenant-name": "tname",
        "owner": "own",
    }[prefix]
    suffix = "@redacted.invalid" if prefix == "owner" and "@" in text else ""
    return f"{label}_{digest}{suffix}"


def _stable_sensitive_scalar(value: Any, *, prefix: str) -> Any:
    """Replace a sensitive scalar without changing its JSON scalar type."""
    if isinstance(value, str):
        return _stable_token(value, prefix=prefix)
    if isinstance(value, int) and not isinstance(value, bool):
        return _REDACTED_INT
    if isinstance(value, float):
        return _REDACTED_FLOAT
    return value


def _anon_token(value: str, *, prefix: str, length: int = 8) -> str:
    """Compatibility helper retained for callers of the original script."""
    if _TOKEN_RE.fullmatch(str(value)):
        return str(value)
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def _redact_words(text: str, patterns: list[re.Pattern[str]]) -> str:
    output = text
    for pattern in patterns:
        output = pattern.sub(_REDACTED, output)
    return output


def _validate_structure(node: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise SanitizationError("structure-too-deep", "JSON nesting exceeds the limit")
    if isinstance(node, dict):
        if len(node) > MAX_COLLECTION_ITEMS:
            raise SanitizationError("collection-too-large", "an object exceeds the entry limit")
        for key, value in node.items():
            if not isinstance(key, str):
                raise SanitizationError("unsupported-structure", "JSON object keys must be strings")
            if len(key) > MAX_STRING_LENGTH:
                raise SanitizationError("string-too-long", "a JSON key exceeds the limit")
            _validate_structure(value, depth=depth + 1)
        return
    if isinstance(node, list):
        if len(node) > MAX_COLLECTION_ITEMS:
            raise SanitizationError("collection-too-large", "an array exceeds the entry limit")
        for value in node:
            _validate_structure(value, depth=depth + 1)
        return
    if isinstance(node, str):
        if len(node) > MAX_STRING_LENGTH:
            raise SanitizationError("string-too-long", "a JSON string exceeds the limit")
        return
    if isinstance(node, float) and not math.isfinite(node):
        raise SanitizationError("invalid-number", "JSON numbers must be finite")
    if node is None or isinstance(node, (bool, int, float)):
        return
    raise SanitizationError("unsupported-structure", "JSON contains an unsupported value type")


def _validate_platform_shape(doc: dict[str, Any], platform: str) -> None:
    if platform == "aa":
        report_suite = doc.get("report_suite")
        if report_suite is None:
            report_suite = doc.get("reportSuite")
        if not isinstance(report_suite, dict):
            raise SanitizationError(
                "unsupported-aa-shape", "AA input requires a report-suite object"
            )
        if not (report_suite.get("rsid") or report_suite.get("RSID")):
            raise SanitizationError("unsupported-aa-shape", "AA report-suite identity is missing")
        return
    if platform == "cja":
        metadata = doc.get("metadata")
        if not isinstance(metadata, dict):
            raise SanitizationError("unsupported-cja-shape", "CJA input requires a metadata object")
        identity = (
            metadata.get("Data View ID")
            or metadata.get("data_view_id")
            or metadata.get("dataViewId")
        )
        if not identity:
            raise SanitizationError("unsupported-cja-shape", "CJA data-view identity is missing")
        return
    raise SanitizationError("unsupported-platform", "platform must be AA or CJA")


def _scalar_values(node: Any) -> list[tuple[str, bool]]:
    values: list[tuple[str, bool]] = []
    if isinstance(node, dict):
        for value in node.values():
            values.extend(_scalar_values(value))
    elif isinstance(node, list):
        for value in node:
            values.extend(_scalar_values(value))
    elif isinstance(node, str):
        values.append((node, len(node) >= 4))
    elif node is not None and not isinstance(node, bool):
        values.append((str(node), False))
    return values


def _sensitive_values(doc: dict[str, Any]) -> list[_SensitiveValue]:
    by_original: dict[str, _SensitiveValue] = {}

    def add(value: Any, prefix: str) -> None:
        for scalar, global_replace in _scalar_values(value):
            if not scalar or _TOKEN_RE.fullmatch(scalar):
                continue
            key = scalar.casefold()
            by_original.setdefault(
                key,
                _SensitiveValue(
                    original=scalar,
                    replacement=_stable_token(scalar, prefix=prefix) if global_replace else scalar,
                    global_replace=global_replace,
                ),
            )

    def walk(node: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized = _normalized_key(key)
                if normalized in _TENANT_ID_KEYS:
                    add(value, "tenant-id")
                elif normalized in _TENANT_NAME_KEYS:
                    add(value, "tenant-name")
                elif normalized in _OWNER_KEYS:
                    add(value, "owner")
                elif (
                    normalized == "name"
                    and path
                    and path[-1]
                    in {
                        "dataview",
                        "reportsuite",
                    }
                ):
                    add(value, "tenant-name")
                walk(value, (*path, normalized))
        elif isinstance(node, list):
            for value in node:
                walk(value, path)

    walk(doc)
    return sorted(
        by_original.values(),
        key=lambda item: (-len(item.original), item.original.casefold()),
    )


def _replacement_plan(sensitive_values: list[_SensitiveValue]) -> _ReplacementPlan:
    global_values = tuple(item for item in sensitive_values if item.global_replace)
    alternatives = "|".join(re.escape(item.original) for item in global_values)
    return _ReplacementPlan(
        exact={
            item.original.casefold(): str(item.replacement)
            for item in global_values
        },
        pattern=(
            re.compile(
                rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
            if alternatives
            else None
        ),
    )


def _replace_text(
    text: str,
    replacements: _ReplacementPlan,
    redact_patterns: list[re.Pattern[str]],
) -> str:
    replacement = replacements.exact.get(text.casefold())
    if replacement is not None:
        text = replacement
    elif replacements.pattern is not None:
        text = replacements.pattern.sub(
            lambda match: replacements.exact[match.group(0).casefold()],
            text,
        )
    return _redact_words(text, redact_patterns)


def _walk_replace(
    node: Any,
    replacements: _ReplacementPlan,
    redact_patterns: list[re.Pattern[str]],
    *,
    path: tuple[str, ...] = (),
) -> Any:
    if isinstance(node, dict):
        output: dict[str, Any] = {}
        for key, value in node.items():
            replaced_key = _replace_text(key, replacements, redact_patterns)
            if replaced_key in output:
                raise SanitizationError(
                    "key-collision", "redaction would collapse distinct object keys"
                )
            normalized = _normalized_key(key)
            prefix: str | None = None
            if normalized in _TENANT_ID_KEYS:
                prefix = "tenant-id"
            elif normalized in _TENANT_NAME_KEYS:
                prefix = "tenant-name"
            elif normalized in _OWNER_KEYS:
                prefix = "owner"
            elif (
                normalized == "name"
                and path
                and path[-1]
                in {
                    "dataview",
                    "reportsuite",
                }
            ):
                prefix = "tenant-name"
            if prefix is not None:
                output[replaced_key] = _replace_sensitive_node(
                    value,
                    prefix=prefix,
                    replacements=replacements,
                    redact_patterns=redact_patterns,
                )
            else:
                output[replaced_key] = _walk_replace(
                    value,
                    replacements,
                    redact_patterns,
                    path=(*path, normalized),
                )
        return output
    if isinstance(node, list):
        return [
            _walk_replace(
                value,
                replacements,
                redact_patterns,
                path=path,
            )
            for value in node
        ]
    if isinstance(node, str):
        return _replace_text(node, replacements, redact_patterns)
    if node is not None and not isinstance(node, bool):
        replacement = replacements.exact.get(str(node).casefold())
        if replacement is not None:
            return replacement
    return node


def _replace_sensitive_node(
    node: Any,
    *,
    prefix: str,
    replacements: _ReplacementPlan,
    redact_patterns: list[re.Pattern[str]],
) -> Any:
    if isinstance(node, dict):
        output: dict[str, Any] = {}
        for key, value in node.items():
            replaced_key = _replace_text(key, replacements, redact_patterns)
            if replaced_key in output:
                raise SanitizationError(
                    "key-collision", "redaction would collapse distinct object keys"
                )
            output[replaced_key] = _replace_sensitive_node(
                value,
                prefix=prefix,
                replacements=replacements,
                redact_patterns=redact_patterns,
            )
        return output
    if isinstance(node, list):
        return [
            _replace_sensitive_node(
                value,
                prefix=prefix,
                replacements=replacements,
                redact_patterns=redact_patterns,
            )
            for value in node
        ]
    if node is None or isinstance(node, bool):
        return node
    return _stable_sensitive_scalar(node, prefix=prefix)


def _iter_strings(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_strings(value)
    elif isinstance(node, str):
        yield node


def _assert_no_residue(
    doc: Any,
    *,
    replacements: _ReplacementPlan,
    redact_patterns: list[re.Pattern[str]],
) -> None:
    for text in _iter_strings(doc):
        if replacements.pattern is not None and replacements.pattern.search(text):
            raise SanitizationError("residue-detected", "a recognized private value remains")
        if any(pattern.search(text) for pattern in redact_patterns):
            raise SanitizationError("residue-detected", "a requested redaction value remains")


def sanitize(
    doc: dict[str, Any],
    *,
    platform: str,
    redact_patterns: list[re.Pattern[str]],
) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise SanitizationError("unsupported-structure", "top-level JSON must be an object")
    _validate_structure(doc)
    _validate_platform_shape(doc, platform)
    sensitive_values = _sensitive_values(doc)
    replacements = _replacement_plan(sensitive_values)
    cleaned = _walk_replace(doc, replacements, redact_patterns)
    _validate_structure(cleaned)
    _validate_platform_shape(cleaned, platform)
    _assert_no_residue(
        cleaned,
        replacements=replacements,
        redact_patterns=redact_patterns,
    )
    return cleaned


def sanitize_aa(doc: dict[str, Any]) -> dict[str, Any]:
    return sanitize(doc, platform="aa", redact_patterns=[])


def sanitize_cja(doc: dict[str, Any]) -> dict[str, Any]:
    return sanitize(doc, platform="cja", redact_patterns=[])


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise SanitizationError(
                "duplicate-key", "input contains an ambiguous duplicate object key"
            )
        output[key] = value
    return output


def _reject_nonfinite(_value: str) -> None:
    raise SanitizationError("invalid-number", "JSON numbers must be finite")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise SanitizationError("input-unavailable", "input JSON could not be read") from exc
    if len(payload) > MAX_INPUT_BYTES:
        raise SanitizationError("input-too-large", "input JSON exceeds the byte limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SanitizationError("invalid-encoding", "input JSON must be UTF-8") from exc
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except SanitizationError:
        raise
    except json.JSONDecodeError as exc:
        raise SanitizationError("invalid-json", "input is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise SanitizationError("unsupported-structure", "top-level JSON must be an object")
    return parsed


def _atomic_write(path: Path, payload: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, staged_name = tempfile.mkstemp(
            prefix=".sanitize-sdr-",
            dir=path.parent,
        )
    except OSError as exc:
        raise SanitizationError("output-unavailable", "output staging could not begin") from exc

    staged = Path(staged_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    except OSError as exc:
        raise SanitizationError(
            "output-failure", "restricted review candidate could not be committed"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with contextlib.suppress(OSError):
            staged.unlink(missing_ok=True)


def _patterns(value: str) -> list[re.Pattern[str]]:
    return [
        re.compile(re.escape(word.strip()), re.IGNORECASE)
        for word in value.split(",")
        if word.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw SDR JSON to sanitize")
    parser.add_argument("--platform", choices=("cja", "aa"), required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the restricted review candidate",
    )
    parser.add_argument(
        "--redact",
        default="",
        help="comma-separated case-insensitive values to replace throughout JSON",
    )
    args = parser.parse_args(argv)

    try:
        raw = _load_json(args.input)
        redact_patterns = _patterns(args.redact)
        cleaned = sanitize(
            raw,
            platform=args.platform,
            redact_patterns=redact_patterns,
        )
        encoded = (
            json.dumps(
                cleaned,
                indent=2,
                sort_keys=False,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        _atomic_write(args.output, encoded)
    except SanitizationError as exc:
        print(f"sanitize error [{exc.code}]: operation aborted", file=sys.stderr)
        return 2
    except Exception:
        print("sanitize error [internal-error]: operation aborted", file=sys.stderr)
        return 2

    digest = hashlib.sha256(encoded).hexdigest()
    print("restricted review candidate written")
    print(f"review digest sha256:{digest}")
    print("manual review required before sharing; automated redaction is incomplete by design")
    return 0


if __name__ == "__main__":
    sys.exit(main())

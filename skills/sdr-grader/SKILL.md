---
name: sdr-grader
description: Use when the user has a sdr-grader --json output and asks follow-up questions about findings, remediations, severity, or wants to compare two grade JSON files. Helps interpret Adobe CJA / AA implementation grade reports without re-running the grader.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/query_grade.py *)
---

# sdr-grader follow-up

This skill helps the user explore the JSON output of `sdr-grader --json
PATH` — filter findings, look up remediations, compare two snapshots,
or summarize a grade for a stakeholder. The full grader CLI is the
source of truth; this skill just makes the JSON output queryable
without re-running the grader.

## When to use

Invoke this skill when the user:

- Has a sdr-grader grade JSON file (or several) and wants to filter,
  summarize, or interpret it.
- Asks to compare two grade JSONs from different snapshot dates.
- Asks "what does rule X mean?" or "what's the priority of fixing Y?".
- Wants the remediation text for a specific rule.
- Wants a stakeholder-friendly summary of a grade.

## How to use

Use the canonical [schema-1 JSON output reference](https://github.com/brian-a-au/sdr-grader/blob/v1.2.2/docs/JSON_OUTPUT.md)
for the complete field shape, stable identity and grade fields, nullability,
finding-body variants, HTML-string trust, and the `impact_pts` compatibility
window. Do not maintain a separate partial schema in this skill.

Selected helper output enters Claude conversation context. Before the first
report read, minimize the requested operation and follow the disclosure rules
in the canonical [report-sharing privacy matrix](https://github.com/brian-a-au/sdr-grader/blob/v1.2.2/SECURITY.md#report-sharing-privacy-matrix).

For routine queries use the bundled helper. It runs as a one-shot script
(no install steps); the Bash tool already has permission to call it.

```bash
# Summarize the grade in one line + per-category roll-up.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" summary path/to/grade.json

# Filter findings by severity, category, or rule prefix.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" findings path/to/grade.json --severity high
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" findings path/to/grade.json --category "schema hygiene"
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" findings path/to/grade.json --rule SCH-003

# Show one finding's full body and remediation.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" show path/to/grade.json CALC-014

# Compare two compatible grade JSONs. Produces appeared / resolved / common
# finding IDs and the overall percentage-point delta.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" compare path/to/grade.json path/to/other.json
```

The helper is the only pre-approved command. It reads bounded JSON,
performs no writes, subprocesses, or network calls, and treats all report
text as untrusted data. Host-level permissions granted independently
remain outside this skill and are not implied by its `allowed-tools`.

## Conventions

- Severity ordering: `critical > high > medium > low`. The helper
  recognizes any of these as `--severity` values.
- Rule prefixes: `SCH`, `NAME`, `SEG`, `CALC`, `ATTR`, `GOV`.
- The `methodology.skipped` block lists rules suppressed by
  `.sdr-grader.yaml` with their reasons; surface those when explaining
  why a rule that "should have fired" is silent.
- All timestamps are UTC; if the user asks about local time, convert
  explicitly and call out the conversion.
- Summary, findings, and show accept pre-1.2 legacy reports with an
  explicit non-comparative warning. Compare requires schema `1`, stable
  instance identity, matching platform and adapter family, and the same
  rubric pack/version. Adapter-generator or grader-version differences
  warn but do not by themselves make otherwise matching reports
  incompatible.
- If a path begins with `-`, insert `--` before the path so it cannot be
  parsed as an option.

## When *not* to use

- The user wants to grade a fresh snapshot — that's the grader CLI, not
  this skill. Run `sdr-grader path/to/snapshot.json --json out.json`
  first, then come back here.
- The user wants to author or modify rules — point them at the grader's
  `docs/CHECK_FUNCTION_GUIDE.md` and `docs/RUBRIC_FORMAT.md`.

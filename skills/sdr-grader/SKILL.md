---
name: sdr-grader
description: Use when the user has a sdr-grader --json output and asks follow-up questions about findings, remediations, severity, or wants to compare two grade JSON files. Helps interpret Adobe CJA / AA implementation grade reports without re-running the grader.
allowed-tools: Bash(python3:*), Read, Glob
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
- Asks "what does rule X mean?" or "what's the impact of fixing Y?".
- Wants the remediation text for a specific rule.
- Wants a stakeholder-friendly summary of a grade.

## How to use

The grade JSON has these top-level fields:

| Field             | Type                                                     |
|-------------------|----------------------------------------------------------|
| `id`              | string — synthetic report ID                             |
| `instance_name`   | string — data view / report suite name                   |
| `grade`           | string — letter grade                                    |
| `overall_pct`     | int — 0-100                                              |
| `categories`      | list of `{name, pct, grade}`                             |
| `findings`        | list of `{id, severity, category, title, body, actions}` |
| `remediations`    | list of `{text, refs, impact_pts}`                       |
| `methodology`     | `{paragraphs, skipped}`                                  |
| `generated_at`    | ISO-8601 timestamp in UTC                                |

For routine queries use the bundled helper. It runs as a one-shot script
(no install steps); the Bash tool already has permission to call it.

```bash
# Summarize the grade in one line + per-category roll-up.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" summary path/to/grade.json

# Filter findings by severity, category, or rule prefix.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" findings path/to/grade.json --severity high
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" findings path/to/grade.json --category schema_hygiene
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" findings path/to/grade.json --rule SCH-003

# Show one finding's full body and remediation.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" show path/to/grade.json CALC-014

# Compare two grade JSONs. Produces appeared / resolved finding IDs and the
# overall pct delta — same comparison the trend report uses.
python3 "${CLAUDE_SKILL_DIR}/scripts/query_grade.py" compare path/to/grade.json path/to/other.json
```

For richer interpretation (drafting an executive summary, writing a
remediation runbook, mapping findings to Jira tickets), read the JSON
directly via Read or jq and synthesize the answer in prose.

## Conventions

- Severity ordering: `critical > high > medium > low`. The helper
  recognizes any of these as `--severity` values.
- Rule prefixes: `SCH`, `NAME`, `SEG`, `CALC`, `ATTR`, `GOV`.
- The `methodology.skipped` block lists rules suppressed by
  `.sdr-grader.yaml` with their reasons; surface those when explaining
  why a rule that "should have fired" is silent.
- All timestamps are UTC; if the user asks about local time, convert
  explicitly and call out the conversion.

## When *not* to use

- The user wants to grade a fresh snapshot — that's the grader CLI, not
  this skill. Run `sdr-grader path/to/snapshot.json --json out.json`
  first, then come back here.
- The user wants to author or modify rules — point them at the grader's
  `docs/CHECK_FUNCTION_GUIDE.md` and `docs/RUBRIC_FORMAT.md`.

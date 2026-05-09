# CI integration

`sdr-grader` is designed to run in CI alongside `cja_auto_sdr` /
`aa_auto_sdr`. The grader is deterministic and produces both an HTML
report card and (with `--json`) a machine-readable JSON output suitable
for dashboards, leaderboards, and gating.

## Exit codes

| Code | Meaning                                   |
|-----:|-------------------------------------------|
| 0    | Success — grade meets `--fail-below` (or no threshold set) |
| 1    | Runtime error (bad input, IO failure, missing tool) |
| 2    | Graded successfully but below `--fail-below` |
| 3    | Rubric / suppression validation failure   |

## GitHub Actions example

```yaml
name: SDR grade

on:
  pull_request:
    paths:
      - 'snapshots/**'
  schedule:
    - cron: '0 6 * * 1'   # Mondays 06:00 UTC

jobs:
  grade:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install sdr-grader
        run: uv tool install sdr-grader

      - name: Run grader
        run: |
          uv tool run sdr-grader snapshots/ \
            --pack strict \
            --output grade.html \
            --json grade.json \
            --fail-below B-

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: sdr-grade
          path: |
            grade.html
            grade.json
```

The `--fail-below` flag turns the grader into a CI gate: PRs that drop
the implementation below the threshold letter fail. Pair it with
`--quiet` to suppress informational stderr output, or omit it to keep
the run summary visible in the action log.

## Reading the JSON output

The JSON file mirrors the HTML report's data model. Top-level fields
include:

| Field                | Type                                  |
|----------------------|---------------------------------------|
| `id`                 | `string` — synthetic report ID         |
| `instance_name`      | `string` — data view / report suite name |
| `grade`              | `string` — letter grade                |
| `overall_pct`        | `int` — 0-100                          |
| `categories`         | `[{name, pct, grade}]`                 |
| `findings`           | `[{id, severity, category, title, body, actions}]` |
| `remediations`       | `[{text, refs, impact_pts}]`           |
| `methodology`        | `{paragraphs, skipped}`                |
| `generated_at`       | ISO-8601 timestamp in UTC              |

Use `jq '.findings[].id'` to extract a list of fired rule IDs in shell,
or load the file in Python via `json.load`.

## Suppressing rules in CI

A project-level `.sdr-grader.yaml` checked into the repo lets reviewers
mute known false positives without forking the rubric pack. The grader
auto-discovers the file in the working directory:

```yaml
suppress:
  - rule: NAME-002
    reason: "We use legacy IDs with hyphens; agreed by team."

severity_overrides:
  CALC-014: medium

category_weights:
  governance_posture: 0.30
```

The skipped rules surface in the rendered report's methodology section
with the recorded reason, so suppressions remain visible to anyone
reading the report.

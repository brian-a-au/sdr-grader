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

permissions:
  contents: read

jobs:
  grade:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          version: "0.11.16"

      - name: Install sdr-grader
        run: uv tool install sdr-grader==1.2.3

      - name: Run grader
        run: |
          mkdir -p reports
          sdr-grader path/to/snapshot.json \
            --pack strict \
            --output reports/sdr-grade.html \
            --json reports/sdr-grade.json \
            --fail-below B- \
            --quiet

      - name: Upload report
        if: ${{ always() && vars.SDR_GRADER_UPLOAD_REPORTS == 'true' }}
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        with:
          name: sdr-grade
          path: |
            reports/sdr-grade.html
            reports/sdr-grade.json
          if-no-files-found: error
          retention-days: 7
```

Replace `path/to/snapshot.json` and the trigger path with repository-appropriate
generic paths. The `--fail-below` flag turns the grader into a CI gate: a grade
below the threshold exits with code 2 after the named reports are written.
`--quiet` suppresses the normal informational summary so implementation details
do not enter the log merely because grading succeeded; errors still appear.

Report upload is disabled unless the repository explicitly defines the Actions
variable `SDR_GRADER_UPLOAD_REPORTS` with the exact value `true`. When opted in,
`always()` preserves the report from a below-threshold run, while
`if-no-files-found: error` prevents a green upload step from hiding a missing
report. Review both files before enabling the variable. In a public repository,
Actions artifacts are not confidential. Seven-day retention is temporal cleanup
only: it is not access control, sanitization, confidentiality, or durable public
release evidence. See the canonical [report-sharing privacy matrix](../SECURITY.md#report-sharing-privacy-matrix)
for log, artifact, HTML, JSON, and Claude-context boundaries.

## Reading the JSON output

The JSON file mirrors the complete report model. Use the canonical
[schema-1 JSON output reference](JSON_OUTPUT.md) for field paths, nested types,
nullability, finding-body variants, HTML-string trust, and the `impact_pts`
compatibility window. For a small CI query, `jq '.findings[].id'` extracts the
fired rule IDs; load the full artifact with `json.load` when a dashboard needs
the complete structure.

CJA generator timestamps using `PDT` or `PST` are interpreted with fixed UTC
offsets, as are explicit ISO offsets, `Z`, `UTC`, and `GMT`. Unknown timezone
abbreviations never consult the host timezone; they follow the existing
deterministic missing-timestamp fallback (`2026-01-01T00:00:00Z`).

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

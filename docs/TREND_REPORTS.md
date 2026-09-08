# Trend reports (`--trend`)

`--trend` grades every dated snapshot in a directory chronologically
and renders a single self-contained HTML showing how the
implementation's grade has moved over time.

## Usage

```bash
sdr-grader path/to/snapshots/ --trend --output trend.html
```

`path/to/snapshots/` must be a directory. The default output filename
is `trend-{instance_id}-{YYYYMMDD}.html`, using the latest snapshot's
timestamp.

## What the report contains

- **Overall grade trajectory** — the score over time with a sparkline.
- **Per-category sparklines** — one per category, so you can see which
  area of the implementation regressed (or improved) and when.
- **Findings churn** — which rules started firing, stopped firing, or
  kept firing across the time range. Useful for confirming that a
  remediation actually landed.

See `examples/trend-example.html` for a fully rendered sample.

## Snapshot ordering

The trend pipeline orders snapshots by a timestamp parsed out of the
filename. Snapshots whose filenames carry no timestamp are skipped. A present
malformed timestamp is an input error (CLI exit 1); it is never truncated to
a valid prefix or silently skipped. Existing reports are preserved on errors.

Recommended convention: include an ISO-8601 date or full timestamp in
the filename, e.g.:

- `snapshot_2026-04-25.json`
- `snapshot_2026-04-25T09-14-00Z.json`
- `snapshot_2026-04-25T09-14-00.125+09-00.json`
- `prod_us_2026-04-25.json`

Anything the loader can extract as an unambiguous timestamp works; the
prefix and extension don't matter. Date-only and naive timestamps mean UTC;
colon, hyphen, and underscore clock separators remain supported. Fractions
and positive/negative UTC offsets are preserved, including filename-safe
offset separators. Equivalent instants retain stable path ordering.

Directory latest selection and `--at` use the same complete filename instant.
Only filenames with no timestamp retain the directory mtime fallback; trend
mode never creates mtime-backed points. For example, `09:00:00+09:00` precedes
`01:00:00Z` on the same date. Corrected ordering can change the selected grade,
trend delta, and latest-point threshold exit; recompute comparisons with one
pinned package version and pack.

## Combining with the other flags

`--trend` composes with the standard flags:

- `--rubric`, `--pack` — choose which rubric runs for every snapshot.
- `--suppress-config` — same suppression config applies to every grade
  in the series, so churn reflects rule firings, not config changes.

`--json`, `--extra-input`, `--distribution-data`, and `--at` are not
supported with `--trend`; the CLI rejects them rather than silently
ignoring an option.

Re-running with a different rubric pack mid-series produces a
visually clean trend but is semantically misleading — the grades
aren't comparable across pack versions. Keep the pack stable for the
duration of a trend you intend to act on.

Pack `2.0` is a comparison boundary. Regenerate a series entirely with
pack `2.0`; do not append its points to stored pack `1.0` results.

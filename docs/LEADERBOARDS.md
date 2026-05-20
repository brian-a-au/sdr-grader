# Internal leaderboards (distribution data)

Teams that grade many implementations — multiple data views, report
suites, business units, or accounts — often want to know more than the
absolute grade. They want to know whether a 72% is above or below the
typical implementation, and which categories tend to be the weakest
across the portfolio.

The grader supports this via a separate "distribution data" file that
the report renders alongside the grade.

## What ships in the box

The bundled `src/sdr_grader/data/distribution.json` is seed percentile
data — illustrative numbers used by the rendered report's distribution
section when you pass `--distribution-data bundled`. It is *not* an
authoritative reference and should not be used to evaluate your
implementation's standing.

For a meaningful leaderboard, build your own distribution from the
implementations you actually grade.

## Workflow

```bash
# 1. Grade every implementation, writing the JSON output of each.
sdr-grader prod_us.json --json grades/prod_us.json --output /dev/null
sdr-grader prod_eu.json --json grades/prod_eu.json --output /dev/null
sdr-grader prod_apac.json --json grades/prod_apac.json --output /dev/null

# 2. Aggregate the JSONs into a single distribution.json.
python scripts/aggregate_distributions.py grades/ -o distribution.json

# 3. Use it as the reference for future grades.
sdr-grader new_snapshot.json --distribution-data distribution.json
```

`aggregate_distributions.py` reads every `*.json` file in the input
directory, extracts the overall and per-category scores, and writes a
file matching the schema of `src/sdr_grader/data/distribution.json`
(overall median / p25 / p75, plus per-category medians).

## The `--distribution-data` flag

- `--distribution-data PATH` — load percentile data from `PATH`.
- `--distribution-data bundled` — use the bundled seed data.
- Omit the flag entirely — the rendered report skips the distribution
  section.

The flag affects only the rendered HTML; the underlying grade math is
unchanged.

## Refresh cadence

Re-aggregate whenever a non-trivial number of implementations are
graded or the rubric pack version changes. Distributions become
misleading once mixed across rubric versions — track them per-pack-
version if you regrade old snapshots with a new pack.

# Internal leaderboards (distribution data)

Teams that grade many implementations — multiple data views, report
suites, business units, or accounts — often want to know more than the
absolute grade. They want to know whether a 72% is above or below the
typical implementation, and which categories tend to be the weakest
across the portfolio.

The grader supports this via a separate "distribution data" file that
the report renders alongside the grade.

> **Pack `2.0` migration:** results from pack `1.0` and `2.0` are not
> comparable. Delete or archive old aggregate distributions, regrade the
> source snapshots with one pack version, and rebuild the leaderboard
> before using it for decisions.

## What ships in the box

The bundled `sdr_grader/data/distribution.json` package resource (stored at
`src/sdr_grader/data/distribution.json` in a source checkout) is seed
percentile data — illustrative numbers used by the rendered report's
distribution section when you pass `--distribution-data bundled`. It is *not*
an authoritative reference and should not be used to evaluate your
implementation's standing.

For a meaningful leaderboard, build your own distribution from the
implementations you actually grade.

## Installed grading workflow

These grading commands use only the installed `sdr-grader` command. Create
the `grades/` directory with your platform's normal file-management tools,
then keep both outputs: the JSON is the aggregation input and the HTML is the
reviewable report.

```bash
sdr-grader prod_us.json --json grades/prod_us.json --output grades/prod_us.html
sdr-grader prod_eu.json --json grades/prod_eu.json --output grades/prod_eu.html
sdr-grader prod_apac.json --json grades/prod_apac.json --output grades/prod_apac.html
```

## Source-checkout aggregation

The aggregation helper is a maintainer utility, not part of the installed
wheel or the `sdr-grader` CLI. Run this step only from the repository root of
a source checkout (ideally the tag matching the grader version that produced
the JSON files):

```bash
python scripts/aggregate_distributions.py grades/ -o distribution.json
```

After aggregation, `distribution.json` is portable. Return to any environment
with the installed CLI and use it for later grades:

```bash
sdr-grader new_snapshot.json --distribution-data distribution.json
```

`aggregate_distributions.py` reads every `*.json` file in the input
directory, extracts the overall and per-category scores, and writes a
file matching the bundled `sdr_grader/data/distribution.json` resource
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

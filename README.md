# sdr-grader

[![Tests](https://github.com/brian-a-au/sdr-grader/actions/workflows/test.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A deterministic, rule-based linter for Adobe Customer Journey Analytics
(CJA) and Adobe Analytics (AA) implementations. It consumes JSON
snapshots from [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr)
and [`aa_auto_sdr`](https://github.com/brian-a-au/aa_auto_sdr), evaluates
them against a versioned, pluggable YAML rubric, and produces a single
self-contained HTML report card plus a machine-readable JSON output. No
LLMs, no API calls — same input + same rubric always yields the same grade.

## What it grades

`sdr-grader` ships two rubric packs:

- **`strict`** — master-cert-grade opinion; tight thresholds. Reflects
  what a senior consultant would flag.
- **`pragmatic`** — looser thresholds, same rule IDs. For teams who want
  a sanity check rather than an audit.

Both packs cover the full v0.1 rule set across six categories: schema
hygiene, naming consistency, segment complexity, calculated metric
maintainability, attribution coverage, and governance posture. See
[docs/RUBRIC_FORMAT.md](docs/RUBRIC_FORMAT.md) for the format and how
to fork.

## Quickstart

```bash
# 1. Install (uv tool, pipx, or any other Python installer).
uv tool install sdr-grader

# 2. Generate a snapshot of your data view (or report suite).
cja_auto_sdr dv_prod_web --format json --output snapshot.json

# 3. Grade it.
sdr-grader snapshot.json --output grade.html

# 4. Open the report.
open grade.html  # macOS; xdg-open on Linux
```

Or pipe directly without writing a file to disk:

```bash
cja_auto_sdr dv_prod_web --format json --output - | \
  sdr-grader - --output grade.html
```

For CI integration with `--fail-below`, see
[docs/CI_INTEGRATION.md](docs/CI_INTEGRATION.md).

## Input modes

| Mode | Invocation | When to use |
|------|------------|-------------|
| File       | `sdr-grader path/to/snapshot.json`               | One-off grade of a single snapshot you already have on disk. |
| Directory  | `sdr-grader path/to/snapshots/`                  | Point at a folder of dated snapshots; picks the most recent by filename timestamp (falls back to mtime). |
|            | `sdr-grader path/to/snapshots/ --at 2026-04-01`  | Same folder, but grade the snapshot closest to (and not after) the given ISO-8601 date — useful for retro grading or reproducing a prior report. |
| Trend      | `sdr-grader path/to/snapshots/ --trend`          | Grade every dated snapshot in the folder and emit a single trend HTML with sparklines and findings churn. |
| Shell-out  | `sdr-grader --dataview dv_prod_web`              | Pull a fresh CJA snapshot live via `cja_auto_sdr` and grade it in one shot — no intermediate file. Requires `cja_auto_sdr` on `PATH`. |
|            | `sdr-grader --rsid prod_us`                      | Same idea against AA via `aa_auto_sdr`. Requires `aa_auto_sdr` on `PATH`. |
| Stdin      | `… \| sdr-grader -`                              | Stream JSON in from another tool without touching disk — pairs with `cja_auto_sdr … --output -` for ephemeral CI runs. |

## Trend reports

Pointed at a directory of timestamped snapshots, `--trend` grades each one
chronologically and renders a single self-contained HTML showing the
trajectory of the overall grade plus per-category sparklines and a
findings churn summary (which rules appeared and disappeared since the
first snapshot). Snapshots whose filenames don't carry a parseable
timestamp (e.g. `snapshot_2026-04-25.json`) are skipped — the trend
needs a stable ordering. See `examples/trend-example.html`.

## Output

- **HTML report card** at `--output PATH` (default
  `grade-{timestamp}.html`) — single self-contained file, no external
  CSS/JS, prints in black-and-white, screenshots cleanly into decks.
- **JSON output** at `--json PATH` — machine-readable representation of
  the same Report. Suitable for CI dashboards and leaderboards.

## Supplementary inputs

Some rules need data the snapshot itself doesn't carry. Attach
arbitrary JSON files at run time with `--extra-input KEY=PATH`
(repeatable):

```bash
sdr-grader snapshot.json --extra-input KEY=path/to/data.json
```

The CLI loads each file and stores it under
`Implementation.supplementary_data[KEY]`. The key name and the JSON
shape are the *rule's* contract — there is no built-in exporter that
produces these files. Operators supply whatever JSON the rule's
docstring asks for.

Rules opt in by reading the key they need and staying silent when it's
absent, so an opt-in rule simply doesn't fire on snapshots that don't
attach it. `LAUNCH-001` in
`src/sdr_grader/rules/checks/supplementary.py` is the worked example
(its docstring documents the expected JSON shape). See
[docs/ADAPTER_GUIDE.md](docs/ADAPTER_GUIDE.md) for the extension
pattern.

## Internal leaderboards

The bundled `src/sdr_grader/data/distribution.json` is seed percentile
data. Teams that grade many implementations internally can build their
own reference distribution:

```bash
# Run the grader on every implementation, collect the JSON outputs.
sdr-grader prod_us.json --json grades/prod_us.json --output /dev/null
sdr-grader prod_eu.json --json grades/prod_eu.json --output /dev/null

# Aggregate into a distribution.json.
python scripts/aggregate_distributions.py grades/ -o distribution.json

# Use it as the reference for new grades.
sdr-grader new_snapshot.json --distribution-data distribution.json
```

## Tuning rules per project

Drop a `.sdr-grader.yaml` in your working directory to suppress noisy
rules, override severities, or rebalance category weights for your
context:

```yaml
suppress:
  - rule: NAME-002
    reason: "We use legacy IDs with hyphens; agreed by team."

severity_overrides:
  CALC-014: medium

category_weights:
  governance_posture: 0.30
```

The grader auto-discovers the file. Suppressions show up in the
rendered report's methodology section with their reasons attached.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management

## Develop

```bash
uv sync                # set up environment
uv run pytest          # run tests (140+)
uv run ruff check      # lint
uv run python scripts/generate_examples.py   # regenerate examples/
```

## Documentation

- [docs/RUBRIC_FORMAT.md](docs/RUBRIC_FORMAT.md) — YAML rubric schema
- [docs/CHECK_FUNCTION_GUIDE.md](docs/CHECK_FUNCTION_GUIDE.md) — adding a new check
- [docs/ADAPTER_GUIDE.md](docs/ADAPTER_GUIDE.md) — adding a new platform
- [docs/CI_INTEGRATION.md](docs/CI_INTEGRATION.md) — using `--fail-below` in CI

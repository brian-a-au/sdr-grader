# sdr-grader

[![PyPI](https://img.shields.io/pypi/v/sdr-grader)](https://pypi.org/project/sdr-grader/)
[![Tests](https://github.com/brian-a-au/sdr-grader/actions/workflows/test.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/test.yml)
[![Lint](https://github.com/brian-a-au/sdr-grader/actions/workflows/lint.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/lint.yml)
[![Version Sync](https://github.com/brian-a-au/sdr-grader/actions/workflows/version-sync.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/version-sync.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](tests/)
[![Tests](https://img.shields.io/badge/tests-601-brightgreen.svg)](tests/)
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

![sdr-grader report card: a CJA implementation graded F at 51%, with per-category scores](https://raw.githubusercontent.com/brian-a-au/sdr-grader/main/docs/assets/report-card.png)

## What it grades

`sdr-grader` ships two rubric packs:

- **`strict`** — master-cert-grade opinion; tight thresholds. For teams
  who want every finding the rubric can produce.
- **`pragmatic`** — looser thresholds, same rule IDs. For teams who want
  a sanity check rather than an audit.

Both packs cover the same six categories — schema hygiene, naming
consistency, segment complexity, calculated metric maintainability,
attribution coverage, and governance posture — and share the same
rule IDs; `pragmatic` just loosens thresholds and demotes severities.
Every rule in the default packs grades against data the snapshot
itself carries, so out-of-the-box runs need no extra files. A few
additional check functions ship registered but unwired — they read
JSON the operator attaches at run time and are intended for forked
rubrics. See [Supplementary inputs](#supplementary-inputs) for the
attachment mechanism and [docs/RUBRIC_FORMAT.md](docs/RUBRIC_FORMAT.md)
for the pack format.

## How it grades

A grade run is a one-way pipeline over typed data:

1. **Adapt** — the platform adapter (`adapters/cja.py` or
   `adapters/aa.py`) normalizes the JSON snapshot into an
   `Implementation` (metrics, dimensions, segments, calculated metrics,
   governance signals).
2. **Run rules** — the engine loops over every rule in the active
   rubric pack and calls its registered Python check function; each
   check returns zero or more `Finding`s.
3. **Score** — for each non-zero-weight category the subtotal is
   `round((1 − fired_severity / total_severity) × 100)`, where the
   severity weights come from the pack's `_meta.yaml`. The overall
   score is the category-weighted average, rounded.
4. **Letter** — the score maps to a letter via the rubric's
   descending `grade_scale` bands.

Because the rubric (category weights, severity weights, grade bands,
rule list) is data, swapping packs swaps the opinion without changing
a line of grader code. The scoring algorithm itself is in
[`src/sdr_grader/core/grade_calc.py`](src/sdr_grader/core/grade_calc.py).

## Quickstart

```bash
# 1. Install (uv tool, pipx, or any other Python installer).
uv tool install sdr-grader

# 2. Generate a snapshot of your data view (CJA) or report suite (AA).
cja_auto_sdr dv_prod_web --include-all-inventory --format json --output snapshot.json   # CJA
aa_auto_sdr  prod_us                              --format json --output snapshot.json   # AA

# 3. Grade it (platform auto-detected from the snapshot).
sdr-grader snapshot.json --output grade.html

# 4. Open the report.
open grade.html  # macOS; xdg-open on Linux
```

`--include-all-inventory` makes `cja_auto_sdr` ship calculated metrics
and segments alongside the dimensions/metrics SDR. Without it, the
calc-metric and segment rule packs grade against empty inputs and stay
silent. `aa_auto_sdr` includes both inventories by default, so no
equivalent flag is needed on the AA side. See the upstream
[Component Inventory Overview](https://github.com/brian-a-au/cja_auto_sdr/blob/main/docs/INVENTORY_OVERVIEW.md)
for the full set of `--include-*` switches.

Or pipe directly without writing a file to disk:

```bash
# CJA
cja_auto_sdr dv_prod_web --include-all-inventory --format json --output - | \
  sdr-grader - --output grade.html

# AA
aa_auto_sdr prod_us --format json --output - | \
  sdr-grader - --output grade.html
```

## Input modes

| Mode | Invocation | When to use |
|------|------------|-------------|
| File       | `sdr-grader path/to/snapshot.json`               | One-off grade of a single snapshot you already have on disk. |
| Directory  | `sdr-grader path/to/snapshots/`                  | Point at a folder of dated snapshots; picks the most recent by filename timestamp (falls back to mtime). |
|            | `sdr-grader path/to/snapshots/ --at 2026-04-01`  | Same folder, but grade the snapshot closest to (and not after) the given ISO-8601 date — useful for retro grading or reproducing a prior report. |
| Trend      | `sdr-grader path/to/snapshots/ --trend`          | Grade every dated snapshot in the folder and emit a single trend HTML with sparklines and findings churn. |
| Shell-out  | `sdr-grader --dataview dv_prod_web`              | Pull a fresh CJA snapshot live via `cja_auto_sdr` and grade it in one shot — no intermediate file. Requires `cja_auto_sdr` on `PATH`; `--include-all-inventory` is passed automatically so calc-metric and segment rule packs grade against populated inputs. |
|            | `sdr-grader --rsid prod_us`                      | Same idea against AA via `aa_auto_sdr`. Requires `aa_auto_sdr` on `PATH`. |
| Stdin      | `… \| sdr-grader -`                              | Stream JSON in from another tool without touching disk — pairs with `cja_auto_sdr --include-all-inventory … --output -` for ephemeral CI runs. |

One run grades one platform. CJA and AA snapshots are not mixed: the
platform is auto-detected per snapshot from its JSON shape, and the
normalized model holds exactly one platform. In single-file or
directory mode, only one snapshot is graded per invocation (siblings
in a directory are ignored). In `--trend` mode, the runner explicitly
errors out (`snapshots in {dir} mix platforms …`) on a mismatch — keep
CJA and AA snapshots in separate folders.

## Output

- **HTML report card** at `--output PATH` (default
  `grade-{timestamp}.html`) — single self-contained file, no external
  CSS/JS, prints in black-and-white, screenshots cleanly into decks.
- **JSON output** at `--json PATH` — machine-readable representation of
  the same Report. Suitable for CI dashboards and leaderboards.

Sample report cards (rendered from the bundled fixtures):

|         | Clean (A) | Messy (F) |
|---------|-----------|-----------|
| **CJA** | [examples/grade-cja-clean.html](https://raw.githack.com/brian-a-au/sdr-grader/main/examples/grade-cja-clean.html) | [examples/grade-cja-messy.html](https://raw.githack.com/brian-a-au/sdr-grader/main/examples/grade-cja-messy.html) |
| **AA**  | [examples/grade-aa-clean.html](https://raw.githack.com/brian-a-au/sdr-grader/main/examples/grade-aa-clean.html)   | [examples/grade-aa-messy.html](https://raw.githack.com/brian-a-au/sdr-grader/main/examples/grade-aa-messy.html)   |

## Trend reports

Pointed at a directory of timestamped snapshots, `--trend` grades each
one chronologically and renders a single self-contained HTML with the
overall trajectory, per-category sparklines, and a findings-churn
summary. See [docs/TREND_REPORTS.md](docs/TREND_REPORTS.md) for the
filename conventions and flag interactions, or
`examples/trend-example.html` for a rendered sample.

## Supplementary inputs

Rules can optionally grade against data the snapshot doesn't carry
by reading from `Implementation.supplementary_data`. Operators feed
that map via `--extra-input KEY=PATH` (repeatable); rules whose key
is absent stay silent, so attaching extra inputs only matters for
rules that ask for them. See
[docs/SUPPLEMENTARY_INPUTS.md](docs/SUPPLEMENTARY_INPUTS.md).

## Internal leaderboards

Teams grading many implementations can build their own percentile
reference from collected `--json` outputs and pass it back as
`--distribution-data` to render comparative context in the report. See
[docs/LEADERBOARDS.md](docs/LEADERBOARDS.md).

## Customizing the rubric

Every layer is tunable: silence a single rule, fork a pack to shift
thresholds, write a new check function, or add a whole new platform.
The lightest mechanism that works is usually a `.sdr-grader.yaml`
suppression — but heavier moves (forking a pack, adding rules) are
supported and documented. See [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md)
for the full customization spectrum and which mechanism fits which need.

## Claude Code skill

The repo ships a Claude Code skill bundle at
[`skills/sdr-grader/`](skills/sdr-grader/) for asking follow-up
questions about a `sdr-grader --json` output without re-running the
grader — filter findings by severity / category / rule, pull up the
body and remediation for one rule, or diff two grades from different
snapshot dates. Install as a plugin (`/plugin install
brian-a-au/sdr-grader`) or as a personal skill; the bundled helper
script also runs as plain Python with no extra dependencies. See
[`skills/sdr-grader/README.md`](skills/sdr-grader/README.md) for
install and usage details, or
[`skills/sdr-grader/SKILL.md`](skills/sdr-grader/SKILL.md) for the
trigger phrases and helper command reference.

## Develop

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                # set up environment
uv run pytest          # run the test suite
uv run ruff check      # lint
uv run python scripts/generate_examples.py   # regenerate examples/
```

## Documentation

Start here:

- [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) — picking the right customization mechanism

Customizing the rubric:

- [docs/ADAPTER_GUIDE.md](docs/ADAPTER_GUIDE.md) — adding a new platform
- [docs/CHECK_FUNCTION_GUIDE.md](docs/CHECK_FUNCTION_GUIDE.md) — adding a new check
- [docs/PROJECT_CONFIG.md](docs/PROJECT_CONFIG.md) — `.sdr-grader.yaml` schema
- [docs/RUBRIC_FORMAT.md](docs/RUBRIC_FORMAT.md) — YAML rubric schema
- [docs/SUPPLEMENTARY_INPUTS.md](docs/SUPPLEMENTARY_INPUTS.md) — `--extra-input` mechanism

Calibration and audit:

- [docs/PLATFORM_COVERAGE.md](docs/PLATFORM_COVERAGE.md) — CJA vs AA
  coverage, calibration corpus, and known AA gaps
- [docs/CALIBRATION_CORPUS.md](docs/CALIBRATION_CORPUS.md) — how the
  108-snapshot corpus behind the default thresholds is assembled
- [docs/threshold_calibration.md](docs/threshold_calibration.md) —
  per-rule distributions + confidence ratings (auto-generated)
- [docs/RUBRIC_AUDIT.md](docs/RUBRIC_AUDIT.md) — premise audit of each
  rule against Adobe documentation; gaps Adobe carries but the rubric
  doesn't grade

Running and reporting:

- [docs/CI_INTEGRATION.md](docs/CI_INTEGRATION.md) — using `--fail-below` in CI
- [docs/LEADERBOARDS.md](docs/LEADERBOARDS.md) — building a distribution reference
- [docs/TREND_REPORTS.md](docs/TREND_REPORTS.md) — `--trend` usage and conventions

Tooling:

- [skills/sdr-grader/README.md](skills/sdr-grader/README.md) — Claude Code skill bundle for grade follow-up Q&A

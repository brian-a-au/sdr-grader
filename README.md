# sdr-grader

[![PyPI](https://img.shields.io/pypi/v/sdr-grader)](https://pypi.org/project/sdr-grader/)
[![Tests](https://github.com/brian-a-au/sdr-grader/actions/workflows/test.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/test.yml)
[![Lint](https://github.com/brian-a-au/sdr-grader/actions/workflows/lint.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/lint.yml)
[![Version Sync](https://github.com/brian-a-au/sdr-grader/actions/workflows/version-sync.yml/badge.svg)](https://github.com/brian-a-au/sdr-grader/actions/workflows/version-sync.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-99%25-brightgreen.svg)](https://github.com/brian-a-au/sdr-grader/tree/v1.2.4/tests)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/brian-a-au/sdr-grader/blob/main/LICENSE)

A deterministic, rule-based linter for Adobe Customer Journey Analytics
(CJA) and Adobe Analytics (AA) implementations. It consumes JSON snapshots
from [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr) and
[`aa_auto_sdr`](https://github.com/brian-a-au/aa_auto_sdr), evaluates them
against a versioned YAML rubric, and produces a self-contained HTML report
card plus machine-readable JSON.

File and directory grading make no network requests or Adobe API calls: the
same input and rubric always produce the same grade. The convenience modes
`--dataview` and `--rsid` are different: they launch a child generator, and
that child calls Adobe APIs before the local grader runs.

![sdr-grader report card: a CJA implementation graded F at 47%, with per-category scores](https://raw.githubusercontent.com/brian-a-au/sdr-grader/v1.2.4/docs/assets/report-card.png)

## What it grades

`sdr-grader` ships `strict` and `pragmatic` rubric packs. Both cover schema
hygiene, naming consistency, segment complexity, calculated metric
maintainability, attribution coverage, and governance posture. `strict` uses
tight, master-cert-grade thresholds; `pragmatic` uses the same rule IDs with
looser thresholds and severities.

Bundled pack `2.0` has 27 rule IDs. Its scores are not comparable with pack
`1.0`, so re-baseline CI thresholds, trends, and leaderboards after upgrading.
Every default rule grades data carried by the snapshot. Optional registered
checks can use operator-supplied JSON; see [Supplementary inputs](#supplementary-inputs).

## How it grades

1. **Adapt** the platform snapshot into a normalized implementation.
2. **Run rules** from the selected rubric pack.
3. **Score** each weighted category from fired and available severity.
4. **Assign a letter** using the pack's descending grade-scale bands.

The scoring implementation is pinned with this release at
[`src/sdr_grader/core/grade_calc.py`](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/src/sdr_grader/core/grade_calc.py).

## First local grade

This auth-free quickstart works from any writable directory after installing
Python 3.11 or newer. It grades a tagged synthetic fixture, so you can confirm
the installation before using production data or configuring Adobe credentials.

Install the released grader with `uv` (or use `pipx` or another isolated Python
tool installer):

```bash
uv tool install sdr-grader
sdr-grader --version
```

Download the v1.2.4 synthetic CJA snapshot.

macOS and Linux:

```bash
curl -fL -o cja_snapshot_clean.json https://raw.githubusercontent.com/brian-a-au/sdr-grader/v1.2.4/tests/fixtures/cja_snapshot_clean.json
```

Windows PowerShell:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/brian-a-au/sdr-grader/v1.2.4/tests/fixtures/cja_snapshot_clean.json" -OutFile "cja_snapshot_clean.json"
```

Grade it with the installed command on macOS, Linux, or Windows:

```bash
sdr-grader cja_snapshot_clean.json --output grade.html --json grade.json --quiet
```

Open the local HTML report:

```bash
open grade.html                 # macOS
xdg-open grade.html             # Linux
```

```powershell
Start-Process .\grade.html      # Windows PowerShell
```

Live snapshots have two separate optional prerequisites:

- **CJA:** install `cja_auto_sdr` using its
  [Installation](https://github.com/brian-a-au/cja_auto_sdr#install-from-pypi-recommended)
  instructions, then configure its
  [Adobe credentials](https://github.com/brian-a-au/cja_auto_sdr#3-configure-credentials).
  Generate with `--include-all-inventory`; without the complete CJA inventory,
  calculated-metric and segment inputs are empty and those rules stay silent.
- **AA:** install `aa_auto_sdr` using its
  [Installation](https://github.com/brian-a-au/aa_auto_sdr#install-from-pypi-recommended)
  instructions, then configure its
  [Adobe credentials](https://github.com/brian-a-au/aa_auto_sdr#3-configure-credentials-adobe-analytics-api-20-oauth-server-to-server).
  AA includes both inventories by default.

The upstream CJA
[Component Inventory Overview](https://github.com/brian-a-au/cja_auto_sdr/blob/main/docs/INVENTORY_OVERVIEW.md)
documents the complete set of `--include-*` switches.

## Using sdr-grader

The following are installed-user workflows. Generate live snapshots only after
installing and authenticating the appropriate prerequisite above:

```bash
# CJA: include the complete component inventory.
cja_auto_sdr dv_prod_web --include-all-inventory --format json --output snapshot.json

# AA: inventory is included by default.
aa_auto_sdr prod_us --format json --output snapshot.json

# Either platform is auto-detected from the resulting JSON.
sdr-grader snapshot.json --output grade.html --json grade.json
```

For an installed streaming workflow on macOS, Linux, or Windows shells with
pipe support:

```bash
cja_auto_sdr dv_prod_web --include-all-inventory --format json --output - | sdr-grader - --output grade.html
aa_auto_sdr prod_us --format json --output - | sdr-grader - --output grade.html
```

### Input modes

| Mode | Invocation | Network behavior |
|---|---|---|
| File | `sdr-grader path/to/snapshot.json` | Local only. |
| Directory | `sdr-grader path/to/snapshots/` | Local only; selects the newest snapshot. |
| Historical | `sdr-grader path/to/snapshots/ --at 2026-04-01` | Local only; selects the closest snapshot not after the date. |
| Trend | `sdr-grader path/to/snapshots/ --trend` | Local only; grades dated snapshots chronologically. |
| CJA child generator | `sdr-grader --dataview dv_prod_web` | `cja_auto_sdr` calls Adobe APIs; complete inventory is requested automatically. |
| AA child generator | `sdr-grader --rsid prod_us` | `aa_auto_sdr` calls Adobe APIs. |
| Stdin | `… \| sdr-grader -` | The grader is local; the producer determines whether the pipeline uses a network. |

One run grades one platform. Keep CJA and AA snapshots in separate directories.
Directory history uses only same-platform, same-instance siblings; trend mode
rejects mixed-platform or mixed-instance input rather than combining it.

### Supplementary inputs

Forked rubrics can read optional JSON from `Implementation.supplementary_data`.
Attach it with repeatable `--extra-input KEY=PATH` flags; a rule whose key is
absent stays silent. The tagged
[supplementary-input contract](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/SUPPLEMENTARY_INPUTS.md)
defines keys, paths, and failure behavior.

## Output

- **HTML report card** at `--output PATH` (default
  `grade-{report-id}.html`) is a single self-contained file with no external
  CSS or JavaScript.
- **JSON output** at `--json PATH` uses schema `1` and contains stable instance,
  adapter, rubric, and grader identity plus the complete report model. See the
  tagged [JSON output contract](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/JSON_OUTPUT.md).

### HTML color packs

Generated HTML supports exactly four built-in color packs, in this public
order: `default`, `ADBE`, `OMTR`, `BLUE`. Select one for a normal report or a
trend report with the case-sensitive `--color-pack` option:

```bash
sdr-grader snapshot.json --color-pack ADBE --output grade.html
sdr-grader snapshots/ --trend --color-pack BLUE --output trend.html
```

The same choice is available to renderer API callers:

```python
from sdr_grader.render import render
from sdr_grader.trend import render_trend

grade_html = render(report, color_pack="OMTR")
trend_html = render_trend(trend, color_pack="BLUE")
```

`--pack` and `--color-pack` are independent. `--pack` selects the scoring
rubric (`strict` or `pragmatic`); `--color-pack` selects only the presentation
palette for generated HTML. It does not enter the report model or separately
written JSON, and does not change findings, scoring, grades, or exit codes.

The named palettes use source swatches as design inspiration only. They are
not official brand assets, contain no logos, and do not imply affiliation,
sponsorship, endorsement, or approval by any company. Reviewed text and
essential-graphic color pairs are tested at WCAG contrast thresholds, but
color is not the only severity cue: reports retain severity text and bordered
structure. Print-specific foreground, background, and border roles are also
tested. Every palette remains embedded in the same self-contained HTML, so
reports continue to work offline without external CSS or JavaScript.

Rendered examples for this release:

| | Clean (A) | Messy (F) |
|---|---|---|
| **CJA** | [CJA clean](https://raw.githack.com/brian-a-au/sdr-grader/v1.2.4/examples/grade-cja-clean.html) | [CJA messy](https://raw.githack.com/brian-a-au/sdr-grader/v1.2.4/examples/grade-cja-messy.html) |
| **AA** | [AA clean](https://raw.githack.com/brian-a-au/sdr-grader/v1.2.4/examples/grade-aa-clean.html) | [AA messy](https://raw.githack.com/brian-a-au/sdr-grader/v1.2.4/examples/grade-aa-messy.html) |

## Troubleshooting

Missing generators, Adobe authentication, incomplete inventories, platform
detection, directory mixing, compatibility warnings, output paths, and privacy
are covered in the tagged
[troubleshooting guide](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/TROUBLESHOOTING.md).

Before sharing an HTML or JSON report, follow the current
[report-sharing privacy matrix](https://github.com/brian-a-au/sdr-grader/blob/main/SECURITY.md#report-sharing-privacy-matrix).

## Integrating sdr-grader

- [CI integration](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/CI_INTEGRATION.md) — use `--fail-below` safely in automation.
- [Trend reports](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/TREND_REPORTS.md) — filename conventions and flag interactions.
- [Internal leaderboards](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/LEADERBOARDS.md) — build a distribution reference from collected JSON outputs.
- [Supplementary inputs](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/SUPPLEMENTARY_INPUTS.md) — attach repeatable `--extra-input KEY=PATH` data.
- [Claude Code skill](https://github.com/brian-a-au/sdr-grader/tree/v1.2.4/skills/sdr-grader) — query a grade without rerunning the grader.

## Extending sdr-grader

Start with the tagged
[customization guide](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/CUSTOMIZATION.md),
then choose the narrowest extension surface:

- [Project configuration](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/PROJECT_CONFIG.md) — suppressions in `.sdr-grader.yaml`.
- [Rubric format](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/RUBRIC_FORMAT.md) — fork or create a YAML pack.
- [Check-function guide](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/CHECK_FUNCTION_GUIDE.md) — add rule logic.
- [Adapter guide](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/ADAPTER_GUIDE.md) — add a platform in a source checkout.

## Maintaining sdr-grader

These are source-checkout workflows. Run them from the repository root after
cloning the [v1.2.4 source tree](https://github.com/brian-a-au/sdr-grader/tree/v1.2.4):

```bash
uv sync
uv run pytest
uv run ruff check
uv run python scripts/build_cja_fixtures.py
uv run python scripts/generate_examples.py
uv run python scripts/generate_grade_examples.py
uv run python scripts/generate_trend_example.py
```

Maintainer references:

- [Platform coverage](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/PLATFORM_COVERAGE.md) — CJA/AA compatibility evidence and known gaps.
- [Calibration corpus](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/CALIBRATION_CORPUS.md) — private compatibility and calibration admission.
- [Threshold calibration](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/threshold_calibration.md) — admitted-cohort status.
- [Rubric audit](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/RUBRIC_AUDIT.md) — rule premises against Adobe documentation.
- [Release checklist](https://github.com/brian-a-au/sdr-grader/blob/v1.2.4/docs/RELEASE_CHECKLIST.md) — publication, recovery, and announcement gates.

## Community

- [Contributing](https://github.com/brian-a-au/sdr-grader/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/brian-a-au/sdr-grader/blob/main/CODE_OF_CONDUCT.md)
- [Security and privacy](https://github.com/brian-a-au/sdr-grader/blob/main/SECURITY.md)
- [Issues](https://github.com/brian-a-au/sdr-grader/issues)

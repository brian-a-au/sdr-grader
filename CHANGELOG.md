# Changelog

All notable changes follow the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
spirit. The version numbers follow [Semantic Versioning](https://semver.org/).

## 1.1.3 — 2026-07-18

Adapter fixes for real-world CJA and AA exports, mirrored from the
sdr-visualizer corpus-fidelity round. No rules, checks, or grades change.

### Fixed

- **CJA adapter.** Real cja_auto_sdr exports carry the generation
  timestamp only under the key "Generated Date & timestamp and
  timezone"; the adapter now reads it, after the existing synthetic
  keys, so `snapshot_taken_at` is populated for real exports.
- **Both adapters.** `created_at` and `modified_at` come back as None
  when the raw export carries a non-string value, instead of passing a
  fabricated value through, and the CJA derived-field `data_type` gets
  the same string cast the metric and dimension paths already used.

## 1.1.2 — 2026-07-17

Trend report bug fixes and small rendering fixes. No rules, checks, or
grades change.

### Fixed

- **Trend report.** The snapshot table keeps its columns aligned when a
  snapshot is missing a category. The page header and container are now
  styled; the template previously referenced CSS classes that no
  stylesheet defined. An empty trend report raises a clear error instead
  of crashing. The trend renderer no longer imports the grading engine,
  restoring the renderer-standalone contract.
- **Date rendering.** Month names come from a fixed English table
  instead of the process locale, and naive datetimes are treated as UTC
  everywhere, so embedding hosts get identical output regardless of
  locale or machine timezone.
- **Charts.** The distribution histogram clamps its inputs and tolerates
  inverted percentiles instead of emitting a rect with negative width.
- **LAUNCH-001** no longer emits an empty paragraph block when a rule
  has no remediation text.

### Docs

- The SCH-005 docstring no longer promises `stale_days` behavior the
  check does not implement; the real check is deferred to 1.2.0.

## 1.1.1 — 2026-07-13

A packaging-only release. No rules, checks, or grades change, so grades
are identical to 1.1.0.

### Fixed

- **Local working artifacts no longer ship in the source distribution.**
  The `.superpowers/` and `.hypothesis/` directories were bundled into the
  sdist because `.gitignore` did not cover them, and hatchling reads
  `.gitignore` to decide what the sdist contains. They are now ignored,
  and `pyproject.toml` excludes them from the sdist target as a second
  guard. The sdist is uploaded to PyPI and is world-readable regardless of
  the git repository's visibility, so these never belonged in it. The
  wheel was already clean and is unchanged.

### Changed

- **Richer PyPI metadata.** Added trove classifiers and keywords to
  `pyproject.toml`. No runtime change.

## 1.1.0 — 2026-07-11

This release adds six rules, removes two rules that a corpus audit showed
could not tell a good implementation from a bad one, and fixes a wide set
of bugs in the adapters, the input pipeline, and the renderer. The default
packs now hold 30 rules across the same 6 categories. Grades can shift
from 1.0.0 because the default packs changed.

### Added

- **Six new rules** in both default packs:
  - `SCH-007` and `ATTR-004` grade CJA Data View settings.
  - `SCH-008` finds cycles between CJA derived fields.
  - `SCH-009` finds CJA derived fields that reference components that do
    not exist.
  - `GOV-007` and `GOV-008` flag calculated metrics and segments that are
    shared but never approved.
- **Default output filenames keyed to the report id.** When you do not
  pass `--output`, the CLI names the file `grade-<report id>.html`. The
  old default used a timestamp, so a batch run that graded several
  instances within the same second wrote them all to one file. (#2)
- **Capped component lists in the report.** A finding now shows at most
  50 affected components plus a line with the count of the hidden ones.
  The `--json` output keeps the full list. (#5)
- **Full inventory in shell-out mode.** Runs started with `--dataview` or
  `--rsid` now pass `--include-all-inventory` to the snapshot tool.

### Changed

- **`ATTR-001` and `ATTR-002` are out of the default packs.** A corpus
  audit (`docs/RUBRIC_AUDIT.md`) showed that `ATTR-001` fired on 100% of
  the metrics it watched, and that every fixture scored the same on
  `ATTR-002`, so its threshold could not separate anything. Both check
  functions stay registered for custom packs.
- **`NAME-001` and `NAME-003` grade again.** The CJA adapter now parses
  tags that arrive as JSON-encoded strings, which is what real snapshots
  contain. Before this fix the two rules matched nothing.
- **Faster rendering of large reports.** The renderer caches compiled
  templates and CSS, and the report skips layout work for findings that
  are off-screen.
- **Docs reorganized.** Reference material moved out of the README into
  `docs/`, including a customization hub, platform coverage, supplementary
  inputs, leaderboards, and the rubric audit.

### Fixed

- **HTML escaping.** The report and trend templates rendered values
  without escaping, and the comparison chart did not escape category
  labels in its SVG. Both are fixed, so snapshot content can no longer
  inject markup into a report.
- **Input handling.** Snapshot files with a UTF-8 BOM load. Timestamps
  with UTC offsets or fractional seconds parse. A snapshot whose platform
  cannot be determined raises a clear error instead of being guessed.
  Directory mode ranks all snapshots on one timestamp scale.
- **Shell-out mode.** The subprocess call has a timeout, decodes output
  as UTF-8, surfaces warnings from the snapshot tool, and reports decode
  failures as the standard invalid-snapshot error.
- **Rule engine.** Pattern and target params are validated when the
  rubric loads instead of failing mid-run. Cycle detection for `SCH-008`
  and `SEG-004` is iterative and deterministic. Expiration blocks with
  NaN or Infinity `numPeriods` no longer crash.
- **AA adapter.** It rejects exports whose dimension, metric, calculated
  metric, or segment sections are missing or not lists. It guards against
  wrongly typed tags, reference lists, and numbers. It counts nesting
  depth the same way the CJA adapter does. It renders nested formula text
  readably and skips blank classification tags.
- **CJA adapter.** Derived-field deduplication normalizes IDs before
  comparing them.
- **CLI.** `--fail-below` works in trend mode, and trend mode rejects
  flags it does not support.

### Discipline

- 402 tests pass and ruff is clean.
- Determinism holds. The same snapshot and rubric still produce
  byte-identical HTML and JSON.

## 1.0.0 — 2026-05-20

First public release. The grader covers the full surface the design SPEC
laid out, plus a Claude Code skill bundle for follow-up question support.
Default rubric thresholds are calibrated against a 108-snapshot corpus of
real CJA + AA production implementations — see
[`docs/threshold_calibration.md`](docs/threshold_calibration.md) for the
distributions and the per-rule confidence rating behind each threshold.

### Added

- **Deterministic, rule-based linter** for Adobe CJA and AA implementations.
  Reads `cja_auto_sdr` / `aa_auto_sdr` JSON snapshots; emits a single
  self-contained HTML report card and a parallel machine-readable JSON.
- **26 rules across 6 categories**: schema hygiene, naming consistency,
  segment complexity, calc metric maintainability, attribution coverage,
  governance posture. Every rule in the default packs grades against
  data the snapshot itself carries; check functions that need external
  evidence (Launch exports, cardinality, ownership, downstream usage,
  SDR docs) ship registered but unwired so operators can include them
  in a forked pack.
- **No cardinality rules.** Rules measure shape, ratio, or correctness —
  never raw counts. See SPEC §11 for the principle and rationale.
- **Two bundled rubric packs (v1.0)**: `strict` (master-cert-grade,
  calibrated p75–p90 thresholds) and `pragmatic` (sanity-check,
  calibrated p90–p95 thresholds, same rule IDs).
- **Four input modes**: file path, snapshot directory (with
  `--at TIMESTAMP` and `--trend`), shell-out via `--dataview` /
  `--rsid`, and stdin.
- **Trend reports**: `--trend` walks a snapshot directory chronologically
  and renders an HTML trajectory with sparklines, per-category deltas,
  and a findings churn summary.
- **Distribution context**: `--distribution-data PATH` (or `bundled`)
  populates the report's overall histogram and category comparison
  charts from a percentile data file.
- **Project-level suppression**: `.sdr-grader.yaml` lets operators
  suppress rules, override severities, and rebalance category weights.
  Skipped rules surface in the rendered methodology section.
- **Supplementary inputs**: `--extra-input KEY=PATH` attaches arbitrary
  JSON files under `Implementation.supplementary_data[KEY]`. The shape
  and key are entirely the rule's contract; the default packs don't
  consume them. Operators who want to grade external evidence write a
  custom rubric pack that targets the registered check functions.
- **JSON output**: `--json PATH` writes the full Report data structure
  for CI dashboards and downstream tooling. Datetimes normalize to UTC
  ISO-8601 with `Z` suffix.
- **CI integration**: `--fail-below GRADE` exits 2 when the grade drops
  below the threshold letter, suitable for PR gates.
- **Claude Code skill bundle** at `skills/sdr-grader/`: SKILL.md plus a
  bundled `query_grade.py` helper for filtering findings, looking up
  remediations, and comparing two grade JSONs from inside Claude Code.
- **Documentation set**: `docs/RUBRIC_FORMAT.md`, `docs/CHECK_FUNCTION_GUIDE.md`,
  `docs/ADAPTER_GUIDE.md`, `docs/CI_INTEGRATION.md`, plus README quickstart.
- **Examples**: clean and messy grade cards per platform
  (`examples/grade-cja-clean.html` A 100%, `examples/grade-cja-messy.html`
  F 44%, `examples/grade-aa-clean.html` A 100%, `examples/grade-aa-messy.html`
  F 39%), a multi-snapshot `examples/trend-example.html`, the original
  visual-contract reference `examples/sample-report.html`, and the
  renderer-output golden `examples/templated-report.html`.

### Discipline

- **Determinism is testable.** The same snapshot + rubric produces
  byte-identical HTML and JSON; tests assert this across two runs.
- **261 tests** cover adapters, rules, engine, grader, CLI, trend
  pipeline, distribution context, supplementary inputs, and the skill
  helper. All pass; ruff clean.
- **Phase discipline preserved**: each commit produced a working,
  reviewable artifact. The full commit graph from scaffold to 1.0.0 is
  visible in the git history.

### Calibration-driven design decisions

Calibration against a 108-snapshot corpus of real CJA + AA production
implementations exposed three rule design problems that this release
addresses:

- **Adobe APIs don't expose `owner` on inline dimensions / metrics.**
  Every tenant in the corpus measured 100% missing owners even after
  normalizing the `"Unknown User"` sentinel. `GOV-004 missing_owners`
  has been moved out of the default packs (still registered for
  operators with their own ownership data).
- **SDR snapshots don't carry downstream usage.** "Orphan" detection
  for segments and calculated metrics in the corpus showed every
  tenant at 100% — segments and calc metrics in production are
  referenced by Workspace projects, dashboards, and alerts, none of
  which the SDR captures. `SEG-003 orphan_segments` and
  `CALC-005 orphan_calc_metrics` have been moved out of the default
  packs.
- **Description discipline is universally poor.** ≥90% of real
  segment-bearing tenants and ≈100% of calc-metric-bearing tenants
  have 100% of those components missing descriptions.
  `SEG-005 segments_missing_descriptions` and
  `CALC-001 calc_metrics_missing_descriptions` are kept in the default
  packs at low severity with near-saturation thresholds (0.95 strict,
  1.0 pragmatic) — they flag the most egregious tenants without
  swamping the grade.

### Registered but not in the default packs

These check functions are registered and tested, but the default
`strict` / `pragmatic` packs don't reference them — they require
evidence the snapshot itself doesn't carry. Operators with that
evidence can include them in a custom rubric pack:

- `orphan_segments` (slot `SEG-003`) and `orphan_calc_metrics` (slot
  `CALC-005`) — require downstream Workspace / dashboard usage data.
- `missing_owners` (slot `GOV-004`) — requires owner attribution data
  that Adobe's APIs don't expose on dims/metrics.
- `doc_drift` (slot `GOV-006`) — reads `last_sdr_update_at` (param),
  `supplementary_data['sdr']['last_updated_at']`, or
  `metadata['SDR Last Updated']`.
- `cardinality_concerns` (slot `SCH-006`) — reads
  `supplementary_data['cardinality']` (a `component_id -> int` map).
- `launch_required_data_elements` (slot `LAUNCH-001`) — reads
  `supplementary_data['launch']`; the canonical worked example for the
  `--extra-input` extension pattern.
- `calc_deprecated_allocations` (slot `CALC-022`) — needs a concrete
  `deprecated_allocations` set via params; default ships placeholder
  values.

### Known limitations

- `cja_auto_sdr` / `aa_auto_sdr` are required to produce the JSON
  snapshots the grader consumes; they are separate projects.
- The bundled `data/distribution.json` ships seed percentile data.
  `scripts/aggregate_distributions.py` lets teams build their own
  internal leaderboards from a directory of grade JSONs;
  `--distribution-data PATH` plugs the result into the report. A
  centralized opt-in submission service is out of scope for this repo.
- README screenshots require manual capture (open
  `examples/grade-cja-messy.html` in a browser and screenshot the page).
  Embedded SVG sparklines + the inlined CSS make the report itself a
  high-fidelity preview when rendered.

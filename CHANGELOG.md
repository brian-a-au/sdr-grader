# Changelog

All notable changes follow the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
spirit. The version numbers follow [Semantic Versioning](https://semver.org/).

## 1.0.0 — 2026-05-09

First public release. The grader covers the full v0.1 + v0.3 + v0.4 surface
the design SPEC laid out, plus a Claude Code skill bundle for follow-up
question support.

### Added

- **Deterministic, rule-based linter** for Adobe CJA and AA implementations.
  Reads `cja_auto_sdr` / `aa_auto_sdr` JSON snapshots; emits a single
  self-contained HTML report card and a parallel machine-readable JSON.
- **32 rules across 6 categories**: schema hygiene, naming consistency,
  segment complexity, calc metric maintainability, attribution coverage,
  governance posture — plus a platform-specific AAEVAR rule. Every rule
  grades against data the snapshot itself carries; rules that required
  external evidence (Launch exports, cardinality, stitching, SDR docs)
  are not part of the default packs.
- **Two bundled rubric packs**: `strict` (master-cert-grade thresholds)
  and `pragmatic` (sanity-check thresholds, same rule IDs).
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
- **Examples**: `examples/grade-clean.html` (A 100%), `examples/grade-messy.html`
  (F 54%), `examples/trend-example.html`, plus the original
  `examples/sample-report.html` and renderer-output golden
  `examples/templated-report.html`.

### Discipline

- **Determinism is testable.** The same snapshot + rubric produces
  byte-identical HTML and JSON; tests assert this across two runs.
- **207 tests** cover adapters, rules, engine, grader, CLI, trend
  pipeline, distribution context, supplementary inputs, and the skill
  helper. All pass; ruff clean.
- **Phase discipline preserved**: each commit produced a working,
  reviewable artifact. The full commit graph from scaffold to 1.0.0 is
  visible in the git history.

### Registered but not in the default packs

These check functions are registered and tested, but the default
`strict` / `pragmatic` packs don't reference them — they require
evidence the snapshot itself doesn't carry. Operators with that
evidence can include them in a custom rubric pack:

- `doc_drift` (formerly `GOV-006`) — reads `last_sdr_update_at` (param),
  `supplementary_data['sdr']['last_updated_at']`, or
  `metadata['SDR Last Updated']`.
- `cardinality_concerns` (formerly `SCH-006`) — reads
  `supplementary_data['cardinality']` (a `component_id -> int` map).
- `aa_evar_distinct_values` (formerly `AAEVAR-001`) — reads the same
  `supplementary_data['cardinality']` map.
- `cja_stitching_unstitched` (formerly `CJASTITCH-001`) — reads
  `supplementary_data['stitching']['unstitched_ratio']` or the same
  field nested in `impl.raw['data_view']['stitching']`.
- `launch_required_data_elements` (formerly `LAUNCH-001`) — reads
  `supplementary_data['launch']`; the canonical worked example for the
  `--extra-input` extension pattern.
- `calc_deprecated_allocations` (formerly `CALC-022`) — needs a
  concrete `deprecated_allocations` set via params; default ships
  placeholder values.

### Known limitations

- `cja_auto_sdr` / `aa_auto_sdr` are required to produce the JSON
  snapshots the grader consumes; they are separate projects.
- The bundled `data/distribution.json` ships seed percentile data.
  `scripts/aggregate_distributions.py` lets teams build their own
  internal leaderboards from a directory of grade JSONs;
  `--distribution-data PATH` plugs the result into the report. A
  centralized opt-in submission service is out of scope for this repo.
- Phase 10 README screenshots require manual capture (open
  `examples/grade-messy.html` in a browser and screenshot the page).
  Embedded SVG sparklines + the inlined CSS make the report itself a
  high-fidelity preview when rendered.

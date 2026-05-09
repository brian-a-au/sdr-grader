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
- **37 rules across 6 categories**: schema hygiene, naming consistency,
  segment complexity, calc metric maintainability, attribution coverage,
  governance posture — plus platform-specific AAEVAR / CJASTITCH rules.
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
- **Supplementary inputs**: `--extra-input KEY=PATH` attaches additional
  JSON exports (Launch property, Workspace project, AEP governance) to
  `Implementation.supplementary_data`. Rules opt in by reading the key
  they need, so they stay quiet on snapshots that don't supply it.
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

### Known limitations

- Several rules ship as documented no-ops awaiting upstream signals:
  `SCH-006` (cardinality), `GOV-006` (doc/code drift),
  `AAEVAR-001` (eVar value distinctness), `CJASTITCH-001` (stitching
  metadata), and the deprecated-allocation set in `CALC-022` is empty
  by default.
- `cja_auto_sdr` / `aa_auto_sdr` are required to produce the JSON
  snapshots the grader consumes; they are separate projects.
- The bundled `data/distribution.json` ships seed percentile data;
  real leaderboard data requires the opt-in submission service tracked
  in the SPEC's deferred work.

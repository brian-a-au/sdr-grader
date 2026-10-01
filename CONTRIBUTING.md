# Contributing to sdr-grader

The grader is intentionally a small, deterministic tool. Contributions
should preserve that. Participation is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md); report vulnerabilities through
the private route in [SECURITY.md](SECURITY.md), not a public issue.

## Repository guidance

[AGENTS.md](AGENTS.md) is the canonical, tool-neutral repository guidance,
including architectural invariants and the locked visual contract. Read it
before making changes. `CLAUDE.md` is a short compatibility wrapper that imports
it for Claude Code; `@AGENTS.md` is Claude-specific syntax, not a universal
AGENTS.md feature. Both are regular files, with shared guidance kept only in
AGENTS.md.

Directory-scoped `AGENTS.md` files may add instructions for a directory and its
subdirectories when a concrete local need exists. Read applicable files before
editing; keep repository-wide instructions in the root file.

## Adding a rule

A rule lands in three places:

1. **YAML entry** in both
   `src/sdr_grader/rules/packs/strict/<category>.yaml` and
   `src/sdr_grader/rules/packs/pragmatic/<category>.yaml` (looser threshold + possibly
   demoted severity).
2. **Check function** in `src/sdr_grader/rules/checks/<category>.py`, registered via
   `@register_check("your_check_name")`.
3. **Unit test** in `tests/test_rules_<category>.py` exercising the
   check with synthetic data.

See [Rubric format](docs/RUBRIC_FORMAT.md) and the
[Check function guide](docs/CHECK_FUNCTION_GUIDE.md) for the shapes.

## Calibration: what's PR-able vs. maintainer-gated

The private, gitignored corpus currently contains 108 real CJA + AA snapshots
used for compatibility testing. None currently meets the explicit human-review
contract for calibration admission, so the default thresholds in
`packs/strict/` and `packs/pragmatic/` remain expert judgment rather than
corpus-calibrated values. Compatibility runs do not substitute for calibration
evidence, and a report not bound to the candidate does not substitute for the
release gate. This shapes what kinds of PRs are easy to merge:

- **PR-able by anyone:**
  - New rules whose firing condition can be demonstrated on a synthetic
    fixture.
  - Bug fixes — incorrect grading logic, adapter crashes (fuzz-found is
    great), renderer regressions.
  - Documentation, examples, CI improvements.
- **Maintainer-gated:**
  - Threshold tweaks to existing rules. These require an explicitly admitted,
    human-reviewed calibration cohort and a candidate-bound run of
    `scripts/calibrate_thresholds.py`; the compatibility corpus alone is not
    enough. Open an issue with the rationale so the maintainer can assess the
    evidence and either land the change or explain why it is not supportable.
  - Severity changes on existing rules — same reason.

If you're adding a rule that needs calibration data, ship the rule with
a defensible round-number threshold and a YAML comment marking it as
provisional. The maintainer will calibrate it before the next release.

See `docs/CALIBRATION_CORPUS.md` for the separate compatibility and calibration
intake requirements, and `docs/threshold_calibration.md` for the current
admitted-cohort distribution evidence.

## Filing issues vs. opening PRs

- **Issue first** for new rules, new categories, structural changes, or
  threshold tweaks. The discussion saves us both time.
- **PR directly** for bug fixes, fuzz-found adapter guards, docs, or
  CI improvements.

## Running locally

All commands in this section are source-checkout workflows run from the
repository root; the referenced tests, scripts, fixtures, and examples are not
installed with the wheel.

```bash
uv sync --locked --all-extras --dev  # set up the locked development environment
uv run pytest                       # full test suite
uv run pytest --cov=src/sdr_grader --cov-report=term  # CI coverage gate
uv run ruff check                   # lint (also run in CI)
uv run ruff format --check <paths>   # check formatting of changed Python files
uv run ruff format <paths>           # auto-format those files
```

Choose checks that cover the changed contract: run focused tests for the
affected adapter, rule, renderer, or script while iterating, and run the full
suite with coverage before marking a code change ready. For prose-only changes,
check links and documented commands; run documentation tests when applicable.
CI tests Python 3.11 and 3.12 and runs Ruff lint; it currently has no format gate.
Limit local formatting to changed Python files.

Changes that can affect generated output also need the
[regeneration sequence](#regenerating-fixtures-and-examples) and a drift check.
Packaging changes need the build and artifact checks documented in the
[release checklist](docs/RELEASE_CHECKLIST.md) and the public-package job in
[CI](.github/workflows/test.yml).

## Dependency maintenance

Dependabot groups weekly Python dependency updates into `uv.lock` and keeps
GitHub Actions updates in a separate group. For a dependency-only PR:

1. Keep the change limited to the lockfile unless the dependency constraint in
   `pyproject.toml` also needs to change.
2. Run `uv sync --locked --all-extras --dev`, `uv run pytest`, and
   `uv run ruff check` from the repository root.
3. Run the fixture and example regeneration sequence below when the dependency
   can affect generated output. If the drift check finds changes, inspect and
   commit the regenerated fixtures or examples with the dependency update.
4. Development-tooling-only updates do not require a package version bump or a
   changelog entry. If a runtime dependency, shipped output, or user-visible
   behavior changes, call out the release impact for maintainer review.

## Regenerating fixtures and examples

After a change that affects the canonical CJA fixtures, rules, or renderer,
run the same source-checkout sequence as the `examples-drift` CI job, from the
repository root. The fixture builder must run before all three example
generators because each later command consumes its committed outputs:

```bash
uv run python scripts/build_cja_fixtures.py
uv run python scripts/generate_examples.py
uv run python scripts/generate_grade_examples.py
uv run python scripts/generate_trend_example.py
```

CI fails any PR where these outputs drift from the committed copies.

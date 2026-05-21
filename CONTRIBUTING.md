# Contributing to sdr-grader

The grader is intentionally a small, deterministic tool. Contributions
should preserve that.

## Invariants

Non-negotiable. PRs that break these will be rejected.

1. **No randomness, no `datetime.now()` in graded output.** Same input
   + same rubric version = byte-identical output. The `examples-drift`
   CI gate enforces this on every PR.
2. **No cardinality rules.** Rules measure shape, ratio, or
   correctness — never raw counts. The same number is healthy for one
   tenant and pathological for another; rules whose firing condition
   reduces to `len(X) > k` are rejected by default.
3. **Renderer stays presentation-only.** No imports from `rules/` or
   `core/grader.py` inside `render/`.

## Adding a rule

A rule lands in three places:

1. **YAML entry** in both `packs/strict/<category>.yaml` and
   `packs/pragmatic/<category>.yaml` (looser threshold + possibly
   demoted severity).
2. **Check function** in `rules/checks/<category>.py`, registered via
   `@register_check("your_check_name")`.
3. **Unit test** in `tests/test_rules_<category>.py` exercising the
   check with synthetic data.

See `docs/RUBRIC_FORMAT.md` and `docs/CHECK_FUNCTION_GUIDE.md` for the
shapes.

## Calibration: what's PR-able vs. maintainer-gated

The default thresholds in `packs/strict/` and `packs/pragmatic/` are
calibrated against a 108-snapshot corpus of real CJA + AA tenants. The
corpus is private (gitignored under `tests/fixtures/private/`) and only
the maintainer can re-run calibration end-to-end. This shapes what kinds
of PRs are easy to merge:

- **PR-able by anyone:**
  - New rules whose firing condition can be demonstrated on a synthetic
    fixture.
  - Bug fixes — incorrect grading logic, adapter crashes (fuzz-found is
    great), renderer regressions.
  - Documentation, examples, CI improvements.
- **Maintainer-gated:**
  - Threshold tweaks to existing rules. These require re-running
    `scripts/calibrate_thresholds.py` against the private corpus, which
    only the maintainer can do. Open an issue with the rationale; the
    maintainer will run the calibration and either land the change or
    explain the distribution that argues against it.
  - Severity changes on existing rules — same reason.

If you're adding a rule that needs calibration data, ship the rule with
a defensible round-number threshold and a YAML comment marking it as
provisional. The maintainer will calibrate it before the next release.

See `docs/CALIBRATION_CORPUS.md` for the corpus intake workflow and
`docs/threshold_calibration.md` for the per-rule distributions and
confidence ratings behind the current thresholds.

## Filing issues vs. opening PRs

- **Issue first** for new rules, new categories, structural changes, or
  threshold tweaks. The discussion saves us both time.
- **PR directly** for bug fixes, fuzz-found adapter guards, docs, or
  CI improvements.

## Running locally

```bash
uv sync                # set up environment
uv run pytest          # full test suite
uv run ruff check      # lint
uv run ruff format     # auto-format
```

After any change to `tests/fixtures/` or rules / renderer, regenerate
the committed examples:

```bash
uv run python scripts/build_cja_fixtures.py
uv run python scripts/build_aa_fixtures.py
uv run python scripts/generate_examples.py
uv run python scripts/generate_grade_examples.py
uv run python scripts/generate_trend_example.py
```

CI fails any PR where these outputs drift from the committed copies.

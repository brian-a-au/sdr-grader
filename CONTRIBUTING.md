# Contributing to sdr-grader

The grader is intentionally a small, deterministic tool. Contributions
should preserve that. Participation is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md); report vulnerabilities through
the private route in [SECURITY.md](SECURITY.md), not a public issue.

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

1. **YAML entry** in both
   `src/sdr_grader/rules/packs/strict/<category>.yaml` and
   `src/sdr_grader/rules/packs/pragmatic/<category>.yaml` (looser threshold + possibly
   demoted severity).
2. **Check function** in `src/sdr_grader/rules/checks/<category>.py`, registered via
   `@register_check("your_check_name")`.
3. **Unit test** in `tests/test_rules_<category>.py` exercising the
   check with synthetic data.

See `docs/RUBRIC_FORMAT.md` and `docs/CHECK_FUNCTION_GUIDE.md` for the
shapes.

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
uv sync                # set up environment
uv run pytest          # full test suite
uv run ruff check      # lint
uv run ruff format     # auto-format
```

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

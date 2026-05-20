# Contributing to sdr-grader

Thanks for your interest. The grader is intentionally a small, deterministic
tool — contributions should preserve that. This document covers how the
project is organized, how to propose a rule, and the few invariants that
must hold.

## Project shape

- **Adapters** parse platform JSON (CJA, AA) into the normalized
  `Implementation` model. Adapters know vocabulary; rules don't.
- **Rules** live as YAML entries in `src/sdr_grader/rules/packs/{strict,pragmatic}/`.
  The data is the rule; check functions live in `rules/checks/` and are
  pure Python.
- **Renderer** is presentation only. It must work with fabricated data
  and never call back into the rule engine.

## Invariants

These are non-negotiable. PRs that break them will be rejected.

1. **No randomness, no `datetime.now()` in graded output.** Determinism is
   a contract — `same input + same rubric = byte-identical output`. The
   `examples-drift` CI gate enforces this by regenerating every example
   on every PR and diffing.
2. **No cardinality rules.** Rules measure shape, ratio, or correctness —
   never raw counts. "You have more than N segments" is folklore dressed
   up as a threshold; the same number is healthy for one tenant and
   pathological for another. See SPEC §11 for the full rationale. Any
   proposed rule whose firing condition reduces to `len(X) > k` is
   rejected by default.
3. **Renderer stays presentation-only.** No imports from `rules/` or
   `core/grader.py` inside `render/`.

## Proposing a new rule

A rule lands in four files:

1. **A YAML entry** in both `packs/strict/<category>.yaml` and
   `packs/pragmatic/<category>.yaml` (looser threshold + possibly
   demoted severity).
2. **A check function** in `rules/checks/<category>.py`, registered via
   `@register_check("your_check_name")`.
3. **A unit test** in `tests/test_rules_<category>.py` exercising the
   check directly with synthetic data.
4. **A fixture update** in `scripts/build_*_fixtures.py` if the messy
   fixtures need to exercise the new rule.

If the rule needs calibration data:

1. Add a measurement function in `scripts/calibrate_thresholds.py`.
2. Run `uv run python scripts/calibrate_thresholds.py` against your
   corpus.
3. Set the rubric thresholds from the resulting distribution rather
   than picking round numbers.
4. Note the source distribution in the YAML `params` block with a
   comment (see existing rules for the pattern).

If the rule needs evidence the snapshot doesn't carry: register the
check function but leave the YAML reference out of the default packs.
Document the required `supplementary_data` shape in the check
docstring. See `cardinality_concerns` or `launch_required_data_elements`
for working examples.

## Adapter changes

Adapters must never crash on a malformed snapshot. The contract is:
either return an `Implementation` or raise `InvalidSnapshotError` with
a clear message. The Hypothesis property tests in
`tests/test_adapter_fuzz.py` enforce this — they generate random and
mutated inputs and fail any non-`InvalidSnapshotError` exception.

If you find a real adapter crash via fuzz, fix the missing guard
rather than catching broadly.

## Running locally

```bash
uv sync                # set up environment
uv run pytest          # full test suite
uv run ruff check      # lint
uv run ruff format     # auto-format
```

`scripts/` contains the fixture / example generators. Re-run after
any change that touches `tests/fixtures/` or `examples/`:

```bash
uv run python scripts/build_cja_fixtures.py
uv run python scripts/build_aa_fixtures.py
uv run python scripts/generate_examples.py
uv run python scripts/generate_grade_examples.py
uv run python scripts/generate_trend_example.py
```

CI will fail any PR where these outputs drift from the committed copies.

## Code style

- Python 3.11+ targeted, `ruff` enforces formatting and lint.
- No comments explaining what code does — name the function or
  variable better. Reserve comments for *why*: hidden constraints,
  non-obvious invariants, links to corpus evidence behind a chosen
  threshold.
- Errors at boundaries (adapters, CLI), trust at the core. Internal
  code should not defensively re-validate what an adapter already
  guaranteed.

## Filing issues vs. opening PRs

- **Open an issue first** for new rules, new categories, or structural
  changes. The discussion saves us both time vs. arriving at the same
  conclusion through review feedback.
- **Open a PR directly** for bug fixes, calibration updates from new
  corpus data, docs improvements, or fuzz-found adapter guards.

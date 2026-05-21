## Summary

<!-- What does this PR do, in 1-3 sentences? Link the issue it closes. -->

## Type of change

- [ ] Bug fix (incorrect grading, adapter crash, renderer regression)
- [ ] New rule (also opened an issue first per CONTRIBUTING.md)
- [ ] Threshold / severity tweak (requires maintainer recalibration — explained in the issue)
- [ ] Docs / examples / CI
- [ ] Other (describe)

## Invariant check

These are non-negotiable per CONTRIBUTING.md. Confirm:

- [ ] No randomness or `datetime.now()` in graded output (determinism contract)
- [ ] No new cardinality rules (`len(X) > k` shapes are rejected)
- [ ] `render/` does not import from `rules/` or `core/grader.py`

## Tests + examples

- [ ] `uv run pytest` passes locally
- [ ] `uv run ruff check` passes
- [ ] If rules or renderer changed, examples regenerated via `scripts/generate_*.py` and the diff is committed (the `examples-drift` CI gate will fail otherwise)

## Notes for the reviewer

<!-- Anything non-obvious: a tricky calibration choice, a subtle invariant
relied on, a fixture that needed updating, a follow-up issue you opened. -->

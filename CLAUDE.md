# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

`sdr-grader` is a deterministic, rule-based linter for Adobe Customer Journey Analytics (CJA) and Adobe Analytics (AA) implementations. It is **not** an AI tool — no LLM calls, no agent loops. The intelligence lives in YAML rubrics and pure Python check functions. Determinism is a contract: same input + same rubric version = byte-identical output.

## Design references

The project is past its spec-driven phase — the repo is the deliverable, and the load-bearing contracts now live in tracked docs and code:

- **Architecture (one-way flow):** README "How it grades" section + `src/sdr_grader/core/grader.py`.
- **Normalized internal model:** `src/sdr_grader/core/models.py` (`Implementation`, `Component`, etc.).
- **Rubric format:** `docs/RUBRIC_FORMAT.md` — the user-facing contract for YAML packs.
- **Adapter contract:** `docs/ADAPTER_GUIDE.md` + the two reference adapters in `src/sdr_grader/adapters/`.
- **Check function shape:** `docs/CHECK_FUNCTION_GUIDE.md` + working examples in `src/sdr_grader/rules/checks/`.
- **Visual contract:** the Jinja templates + CSS in `src/sdr_grader/render/templates/` and `render/static/`. Locked — do not redesign.
- **Locked decisions:** no randomness or `datetime.now()` in graded output (determinism is a contract; the `examples-drift` CI gate enforces it). No cardinality rules — rules measure shape, ratio, or correctness, never raw counts like `len(X) > k`. Renderer stays presentation-only (no imports from `rules/` or `core/grader.py` inside `render/`).

## Develop

```bash
uv sync                # Set up environment
uv run pytest          # Run tests
uv run ruff check      # Lint
uv run ruff format     # Auto-format
```

## Architectural rules of the road

- **Adapters know vocabularies; rules don't.** Rules operate on the normalized model. Platform-specific rules opt in via `platforms: [cja]` or `[aa]` in YAML.
- **Rubric is data, not code.** Adding a rule = a YAML entry. Adding a *kind* of check = a Python function plus a YAML reference.
- **Renderer is presentation only.** It must work standalone with fabricated data and never call back into the rule engine.
- **No randomness, no `datetime.now()` in graded output.** Determinism is testable; don't break it.

## When in doubt

Prefer fewer features done well over more features done poorly. Surface ambiguity as a GitHub issue rather than guessing.

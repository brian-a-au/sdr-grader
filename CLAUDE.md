# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

`sdr-grader` is a deterministic, rule-based linter for Adobe Customer Journey Analytics (CJA) and Adobe Analytics (AA) implementations. It is **not** an AI tool — no LLM calls, no agent loops. The intelligence lives in YAML rubrics and pure Python check functions. Determinism is a contract: same input + same rubric version = byte-identical output.

## The spec

The full project spec lives **outside the repo** at `../sdr-grader/SPEC.md` in the local working directory (gitignored intentionally — the working folder is preserved as a reference area, the repo is the deliverable). Read it end-to-end before scaffolding or extending anything. Sections of particular load:

- §3 Visual contract (locked, do not redesign)
- §4 Architecture (one-way flow: input → adapter → model → rules → Report → renderer)
- §5 Normalized internal model (the contract between adapters and rules)
- §6 Rubric format (YAML rules + Python check functions)
- §8 Build phases (do not skip; do not merge)
- §11 Decisions already made (do not relitigate)

## Phase discipline

Each phase in §8 produces a single reviewable artifact. Don't proceed to phase N+1 until phase N is reviewed. Don't bundle phases. The scaffolding here is **Phase 0 only**: directory structure, project metadata, CI, and a smoke test.

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

Prefer fewer features done well over more features done poorly. Surface ambiguity as a GitHub issue rather than guessing — the open questions list in SPEC §13 is a starting point.

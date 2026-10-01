# AGENTS.md

Canonical, tool-neutral guidance for contributors and coding agents working in this repository.

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

## Development and verification

Run source-checkout commands from the repository root. Use
[CONTRIBUTING.md](CONTRIBUTING.md#running-locally) for setup, test, lint, and
format commands and guidance on choosing relevant checks. Follow its
[fixture and example regeneration sequence](CONTRIBUTING.md#regenerating-fixtures-and-examples)
when a change can affect generated output. For packaging changes, follow the
[release checklist](docs/RELEASE_CHECKLIST.md) and the public-package job in
[CI](.github/workflows/test.yml) to build and verify the wheel and sdist.

## Repository guidance and pull requests

This root file governs the repository. Directory-scoped `AGENTS.md` files, when
needed, should contain only guidance specific to that directory and its
subdirectories; read applicable guidance before editing. Add a nested file only
for a concrete local need, and keep shared guidance here.

`CLAUDE.md` is a regular-file compatibility wrapper that imports this file for
Claude Code. That import syntax is Claude-specific, not a universal AGENTS.md
feature. The bundled `skills/sdr-grader/SKILL.md` and Claude plugin are a separate
integration; repository guidance does not change their behavior.

PR titles and bodies must contain no Compound Engineering badge, link,
attribution, or generated-by text. When using its shipping workflow, select
`branding:off`.

## Architectural rules of the road

- **Adapters know vocabularies; rules don't.** Rules operate on the normalized model, not platform-specific raw payloads; see the [rule input boundary](docs/ADAPTER_GUIDE.md#rule-input-boundary). Platform-specific rules opt in via `platforms: [cja]` or `[aa]` in YAML.
- **Rubric is data, not code.** Adding a rule = a YAML entry. Adding a *kind* of check = a Python function plus a YAML reference.
- **Renderer is presentation only.** It must work standalone with fabricated data and never call back into the rule engine.
- **No randomness, no `datetime.now()` in graded output.** Determinism is testable; don't break it.

## When in doubt

Prefer fewer features done well over more features done poorly. Surface ambiguity as a GitHub issue rather than guessing.

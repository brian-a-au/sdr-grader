# sdr-grader

A deterministic, rule-based linter for Adobe Customer Journey Analytics (CJA) and Adobe Analytics (AA) implementations. It consumes JSON snapshots from [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr) and [`aa_auto_sdr`](https://github.com/brian-a-au/aa_auto_sdr), evaluates them against a versioned, pluggable YAML rubric, and produces a single self-contained HTML report card plus a machine-readable JSON output. No LLMs, no API calls — same input + same rubric always yields the same grade.

## Status

Pre-release. Phase 0 scaffold only — see the build phases roadmap for what lands when.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management

## Develop

```bash
uv sync
uv run pytest
uv run ruff check
```

## License

MIT

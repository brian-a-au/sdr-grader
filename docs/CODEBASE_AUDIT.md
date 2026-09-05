# Codebase audit — September 2026

Scope: current main after Dependabot #54 and #53; audit changes are a separate
branch. The original checkout was stale and clean. It was fast-forwarded before
implementation. No AGENTS.md was found; CLAUDE.md, CONTRIBUTING.md, CI workflows,
and the adapter/check/rubric contracts govern this review.

## Review record

| Area | Findings and disposition |
| --- | --- |
| CLI and output publication | Reviewed dispatch, extra inputs, distribution, trend, exit codes, and staged writes. Keep path validation and error boundaries: they protect inputs and partial-write behavior. |
| Input loading, history, shell-out | Reviewed file/stdin/directory selection, same-instance evidence, bounded child streams and cleanup. Keep separate history adaptation and child-process limits; removing validation changes which malformed siblings count as history. |
| AA/CJA adapters and model | Reviewed platform mappings, definition/reference walkers, normalized values, structure budgets and compatibility helpers. Preserve vocabulary differences and public model fields. |
| Scoring, registry, rubric, suppression | Consolidate duplicate score-to-letter implementation while preserving both import paths. Keep registry and validation: custom YAML packs and checks are documented extension points. Component suppression remains a product question. |
| Rule checks: all six categories and supplementary | Consolidate six finding constructors in the existing shared helper module. Remove speculative naming import and unreachable empty-total guards. Preserve all registered checks, including checks absent from default packs. Remove the NaN-only early return where the general non-string/non-mapping fallback already returns None. |
| HTML/JSON/SVG, colors, truncation, trends | Reviewed view construction, escaping, template/CSS caching, display caps, and trend traces. Remove identity-only distribution mapping. Keep JSON deep serialization and compatibility aliases. |
| Tests | Inspected coverage by subsystem, assertion patterns, duplicate function bodies and cleanup-related tests. Remove import/type-only smoke check; CLI, version sync and installed-wheel tests cover imports/version behavior. Remove machine-speed assertion while retaining the 10,000-metric test's zero-comparison assertion and pairwise oracle. Determinism assertions comparing repeated calls are meaningful and retained. |
| Packaging and dependencies | Pydantic has no imports or documented use in package, scripts, tests, or plugin. Remove it and its exclusive transitive dependencies. Jinja2 and PyYAML are used. |
| Development/release tooling | Reviewed workflows, entry points, I/O sites and release validators; focused on candidate identity, bounded requests, hash locks and packaging checks. Retain release safeguards; their complexity enforces documented release contracts. No release/deploy workflow was run. |
| Calibration, sanitization, bundled query helper | Reviewed entry points, data flow, validation/replacement and comparison logic with tests. Keep independent script boundaries and sanitization passes: helper ships standalone and sanitization must check residue. No private corpus or live Adobe run. |

## Implemented batches

1. Dependabot: Actions #54 merged independently. Python #53's stale version
   assertion changed to enforce exact pins, input/lock agreement, and SHA-256
   hashes without hard-coding releases. All 1,046 tests passed locally (99.09%
   coverage); both Python CI versions and packaging checks passed after the
   final base update. Both PRs are merged.
2. Audit cleanup: shared finding construction, grading re-export, identity-map
   removal, unused dependency/import removal, unreachable guards, and two
   low-value test assertions. Focused checks: 260 passed.
3. Performance: replace Python's per-character surrogate scan with a compiled
   character-range regex, retaining the same rejected Unicode range and error.
   Remove a repeated dict type check in the structure traversal. Existing
   surrogate, Unicode, exact budget-boundary, adapter and fuzz tests cover the
   change (168 focused tests passed).

## Performance evidence

macOS arm64, CPython 3.11.6, same bundled fixtures and dependency versions.
Median of seven repeats, ten calls per repeat, warmed imports; JSON disk loading
and rubric loading excluded. Compared pre-audit dependency branch `dd8bdd6`
against the audit changes. HTML and canonical JSON SHA-256 hashes match for all
four fixtures. Rendering timings were effectively unchanged; no rendering or
full CLI speedup is claimed.

| Fixture | Structure validation before → after (ms) | Adapt + grade before → after (ms) | Adapt + grade ratio |
| --- | --- | --- | --- |
| AA clean | 0.484 → 0.197 | 1.072 → 0.777 | 1.38× |
| AA messy | 0.826 → 0.383 | 1.825 → 1.272 | 1.43× |
| CJA clean | 1.217 → 0.416 | 2.274 → 1.337 | 1.70× |
| CJA messy | 10.109 → 3.477 | 16.690 → 9.423 | 1.77× |

Reproduce from each checkout with its environment (timings vary by host):

```bash
uv run python - <<'PYTHON'
import hashlib
import json
import statistics
import timeit
from pathlib import Path
from sdr_grader.input.adapt import adapt_snapshot
from sdr_grader.core.grader import grade
from sdr_grader.core.structure_limits import validate_snapshot_structure
from sdr_grader.render import render
from sdr_grader.render.json_output import report_to_dict
from sdr_grader.rules.rubric import load_rubric

rubric = load_rubric('src/sdr_grader/rules/packs/strict')
for path in sorted(Path('tests/fixtures').glob('*snapshot*.json')):
    snapshot = json.loads(path.read_text())
    def adapt():
        return adapt_snapshot(snapshot, source=str(path), platform_override=None)
    report = grade(adapt(), rubric)
    render(report)
    for name, fn in [
        ('validate', lambda: validate_snapshot_structure(snapshot, label='snapshot')),
        ('adapt', adapt),
        ('adapt_grade', lambda: grade(adapt(), rubric)),
        ('render', lambda: render(report)),
    ]:
        ms = statistics.median(timeit.repeat(fn, number=10, repeat=7)) * 100
        print(path.name, name, round(ms, 4))
    for payload in [render(report), json.dumps(report_to_dict(report), sort_keys=True)]:
        print(hashlib.sha256(payload.encode()).hexdigest())
PYTHON
```

Removing Pydantic also removes annotated-types, pydantic-core,
typing-extensions, and typing-inspection from the lock. This reduces installed
packages by five; installation time and size were not benchmarked.

## Verification

- Dependency baseline: 1,046 tests, 99.09% coverage; audit: 1,045 tests, 99.08%
  coverage on both Python 3.11.6 and 3.12.1. The one removed test only checked
  that an imported version was a string. No remaining local test failures.
- Ruff and version sync passed. Generated fixtures and all examples have no diff.
- Release validator lock regenerates identically using CI's uv 0.11.16 and the
  existing lock as input. A fresh solve without that lock selected newer
  transitive dependencies; those unrelated upgrades were not applied.
- Local wheel/sdist build, strict Twine metadata checks and the repository's
  artifact validator passed. Pinned v1.2.2 compatibility check passed for
  scores, findings, categories, exit codes, trends and JSON schema.
- GitHub audit PR checks: pending at preparation time.

## Remaining decisions and limitations

- Component-level suppression is a documented pass-through because findings
  lack structured component identity. Implementing it changes grading semantics.
- Governance timestamp parsing intentionally accepts fewer formats than report
  timestamps. Unifying these parsers changes grades and requires a rubric decision.
- Deprecated allocation placeholders and unwired checks remain available to
  custom rubrics. Removing them would break that supported extension surface.
- Dense near-duplicate reference sets can still yield quadratic candidate/output
  size. Capping them changes complete JSON findings; no new policy was introduced.
- Coverage is a subsystem review with targeted line-level inspection and automated
  scans, not a claim that every line of release tooling, documentation, fixture,
  or generated HTML was manually audited. Private-corpus calibration, live Adobe
  generators, Windows process behavior, and production publishing are unverified.

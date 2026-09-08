# Grading evidence correctness — package 1.3.0

This disposition addresses findings 3, 4, 7, 8, and 9 from the
2026-09-07 audit (retained locally). The historical audit,
reproduction scripts, and recorded outputs remain unchanged. The reviewed
baseline is v1.2.9, commit `9687fcc66622d454cc121cd49daa319c0c01a939`.

Rubric pack `2.0`, JSON schema `1`, rule IDs, thresholds, severities, category
weights, grade bands, CLI options, and scoring arithmetic remain unchanged.
Package version distinguishes these corrections. Comparing trends across
different package versions can mix different evidence interpretations, even
when both report the same rubric version.

## Intended changes

The numeric examples below refer to the synthetic strict-pack reproductions;
real score changes depend on the effective rules and other findings. The
compatibility matrix covers strict and pragmatic packs separately.

| Audit issue | v1.2.9 behavior | v1.3.0 behavior |
|---|---|---|
| 3: boolean governance evidence | Textual `false` could hide GOV-001/GOV-003: 100/A instead of 78/C+, A gate exit 0 instead of 2. Truthy objects could also pass. | Boolean/textual false yield equal findings, scores, and gates. Unsupported flags fail as input errors. |
| 3: CJA enabled settings | Textual `false` could activate ATTR-004 or SCH-007; the persistence example scored 98 instead of 100. | Disabled settings remain disabled. Malformed consumed enabled flags and selected nested models fail contextually. |
| 4: filename instants | `09:00:00+09:00` was treated as later than `01:00:00Z`: scores `[100, 89]`, delta -11, latest A gate exit 2. | Complete UTC instants produce `[89, 100]`, delta +11, latest 100/A, exit 0. Fractions and cutoff boundaries are retained. |
| 7: time-decay description | Explicit time-decay prose without `attribution` fired ATTR-004: 90/A−, A gate exit 2. | `time decay`/`time-decay`, including case variants, acknowledge the override: 100/A, exit 0. Unrelated text still fires. |
| 8: conflicting segment IDs | Row order could hide a cycle: score 100 or 97. | Both orders fail before scoring with a contextual invalid-input error; no score or new report. |
| 9: custom governance timestamps | Offset/fractional dates could suppress GOV-002/GOV-006 while equivalent `Z` dates fired. Isolated custom packs scored 100/A rather than 0/F. | Equivalent supported instants produce equal decisions, scores, and exits (in that example, 0/F and A gate exit 2). |

## Accepted evidence and migration

Governance flags and CJA `enabled` accept booleans and trimmed, case-insensitive
`true`/`false` strings. Missing/null evidence falls through; explicit false
selects its source. Numbers including 0/1, other strings, lists, and objects
are invalid flags. Governance precedence is custom parameters, runtime
same-instance history when applicable, then metadata. Only the selected source
is validated; agreeing aliases are accepted and conflicts rejected. Consumed
snapshot errors return exit 1 and consumed custom-override errors return exit 3.

Filename timestamps preserve positive/negative UTC offsets and fractional
seconds. Date-only and naive timestamps still mean UTC, and existing colon,
hyphen, and underscore clock separators remain supported. Alphabetic filename
labels remain outside the token. Malformed complete tokens return exit 1 rather
than being truncated or replaced by mtime. No-token filenames retain directory
mtime fallback and trend skipping. Equivalent instants retain stable ordering.
Instants outside Python's representable UTC range are unavailable rather than
raising an uncaught overflow: filename selection rejects them contextually,
and custom governance checks retain their invalid-date no-op policy.

Every normalized segment ID must identify equal complete normalized records.
Reference order and repeated edges are canonicalized for comparison only;
records and inventory counts are not changed. Equal duplicates, unique chains,
cycles, external references, bare IDs, and cross-kind ID reuse remain valid.
Conflicts are rejected by both adapters and the public grader. Invalid optional
history siblings are ignored; invalid selected or timestamped trend snapshots
fail. Reconcile conflicting source records rather than changing row order.

Custom GOV-002/GOV-006 use the existing shared UTC parser, including ISO offsets,
fractions, naive/date-only inputs, and its fixed GMT/UTC/PST/PDT abbreviation
allowlist. The explicit reference, signal precedence, whole-day age arithmetic,
and strict threshold comparisons remain. Source date text may still appear in
a finding, even when its interpreted instant is identical.

Input errors do not create new success reports and preserve existing output
files. Re-run stored evidence using one pinned package/pack combination, inspect
the corrected findings or errors, and then rebaseline CI thresholds deliberately.

## Reproducible verification

Focused proof-first tests cover each correction and its negative controls:

- `tests/test_boolean_evidence.py` and retained governance/attribution/CLI tests.
- `tests/test_filename_timestamp_offsets.py` and retained input/trend/time tests.
- `tests/test_rules_attribution.py` and `tests/test_correctness_evidence.py`.
- `tests/test_duplicate_segment_ids.py` and retained adapter/grader/segment tests.
- `tests/test_governance_timestamp_equivalence.py` and retained date tests.

The release compatibility script retains its immutable v1.2.2 comparison and
adds a separate v1.2.9 comparison against the full reviewed commit above.
Successful outputs and reportless input/rubric errors have explicit expectations;
unexpected finding, score, category, or exit drift must fail comparison.

The authoritative isolated comparison passed with uv 0.11.16: the original
v1.2.2 gate and 65 exact v1.2.9-to-candidate outcomes. The latter contains 37
changed and 28 unchanged outcomes, including all eight public platform/pack
fixture combinations, 16 candidate snapshot errors, and one rubric error.
See the full reviewed expectations and JSON-pointer deltas in
`tests/fixtures/correctness_1_3/`. Pragmatic does not consume GOV-003 metadata;
its unchanged document-presence outcomes are intentional.

Run `python3 scripts/verify_release_compatibility.py --uv uv`, the full coverage
suite, lint, version sync, fixture/example generation and drift checks, and the
release workflow's distribution/install checks. Hosted release evidence is
recorded separately from local regression evidence; a skipped verifier is never
a pass.

## Remaining limits

ATTR-004 is a bounded prose heuristic; it does not prove model correctness or
documentation quality. Custom date checks still skip genuinely invalid or
unavailable dates and remain absent from bundled packs. No new evidence-
completeness policy or rubric calibration is introduced. The prior CJA
reference, AA optional-definition, stable-score, suppression, and report-count
corrections remain required regressions.

The existing 108-entry private compatibility manifest (100 CJA, 8 AA) passed
both bundled packs through adaptation, grading, plugin summary/findings/show/compare
queries, and repeated rendering during candidate validation. The complete local
suite passed 1,594 tests with 99.04% source coverage; lint passed. Only aggregate evidence is reported; no private data is published.
Zero entries are admitted for calibration, and these comparisons are not an
accuracy-calibration claim. Public installation
success requires the actual v1.3.0 artifact and public matrix evidence; hosted
synthetic verifier-recovery tests establish only the separate release prerequisite.

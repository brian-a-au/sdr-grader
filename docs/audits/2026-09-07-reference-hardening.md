# CJA reference evidence hardening after v1.2.8

Baseline: current `origin/main` / `9d0217436349d9dfe178b6e2b5028c0cac3bbb03`,
including PRs #60, #62, and #61. No applicable AGENTS.md was found in this
repository or its parents. Read CLAUDE.md, CONTRIBUTING.md, adapter/model,
rubric, JSON, suppression and trend contracts, and the six requested audit,
coverage and calibration documents. Prior audit output is historical evidence;
the complete reproducer was rerun. Baseline suite: 1,175 passed.

## Confirmed fixes

### 1. P1: canonical CJA references lost behind exporter abbreviations

Baseline `src/sdr_grader/adapters/cja.py:310-324` parses the definition but
constructs references exclusively from summaries. Upstream-shaped Sessions
input falsely fires SCH-002 and CALC-002: strict **71/C-minus, exit 2** at
`--fail-below C`; canonical summary spelling alone yields **78/C+, exit 0**.

Minimal snapshot:

```json
{"metadata":{"Data View ID":"dv1","Tool Version":"3.11.7"},"metrics":[],"dimensions":[],"calculated_metrics":{"metrics":[{"id":"cm1","name":"Session count","description":"Counts sessions","metric_references":["visits"],"definition_json":"{\"func\":\"calc-metric\",\"formula\":{\"func\":\"metric\",\"name\":\"metrics/visits\"}}"}]}}
```

Reproduce on either baseline or candidate:

```sh
.venv/bin/python docs/audits/2026-09-07-reproductions/adapters_repro.py
.venv/bin/python -m sdr_grader /tmp/adapter-healthy-exported.json --fail-below C --output /tmp/healthy.html --json /tmp/healthy.json
```

Expected and fixed: both healthy representations **78/C+, exit 0**. The
remaining governance penalties are the explicit bundled policy, not part of
this defect. The fix at `adapters/cja.py:348` reads typed definition references,
including nested named operands and filter context. Complete namespace/path
identity is preserved. A shortened summary expands only with one matching
reference of the same kind in that definition. Ambiguous abbreviations remain
unresolved; a matching inventory suffix alone never establishes identity.
Unmatched summary references survive partial/unsupported definitions.

### 2. P2: records-only references silently discarded

Baseline `adapters/cja.py:651-673` accepts native/JSON arrays but drops plain
reference text; segment normalization at line 423 also omits the tabular
`segment_references` alias. In the minimal snapshot above replace `visits`
with `deleted` in both fields, then compare `["deleted"]` and `"deleted"`.
Full input yields **71/C-minus, exit 2**; records-only incorrectly yields
**78/C+, exit 0**. The same command creates `/tmp/adapter-broken-full.json`
and `/tmp/adapter-broken-records.json`.

Expected and fixed: both broken representations **71/C-minus, exit 2**.
`adapters/cja.py:406` adds inventory-specific comma-separated parsing; segment
normalization accepts both reference aliases. Native/JSON list members that
are null, false, zero, or objects no longer become invented string IDs.
Blank and `-` sentinels remain empty. Malformed JSON-looking summaries retain
the optional empty fallback, while decoding/structure/Unicode limit failures
remain contextual input errors (exit 1, no new HTML or JSON).

The fix does not assert live breakage from an incomplete inventory: unresolved
wording and source-platform-first remediation from #60 remain. Duplicate IDs,
disabled/deleted state policy and inventory completeness are not silently
resolved by this patch. AA and the shared defensive helpers are unchanged;
#62's malformed optional AA definition fallback remains intact.

## Independent contract evidence

Checked current Adobe primary sources on 2026-09-07:

- [CJA Metrics API](https://developer.adobe.com/cja-apis/docs/endpoints/metrics/)
  identifies `metrics/visits` as Sessions.
- [CJA calculated metrics](https://developer.adobe.com/cja-apis/docs/endpoints/calculatedmetrics/)
  documents `definition.version: [1,0,0]`, `calc-metric`, named divide operands,
  and typed `metric/name` nodes. The
  [validation example](https://developer.adobe.com/cja-apis/docs/endpoints/calculatedmetrics/validate)
  confirms canonical identity metrics and data-view-specific validity.
- [Adobe Analytics segment definition examples](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/segments/examples)
  establish `attr/name` versus comparison literals for Analytics 2.0. CJA's
  public segment endpoint page does not enumerate every AST variant; do not
  interpret these examples as a complete versioned CJA segment grammar.

Inspected upstream cja_auto_sdr **3.11.7** (`98dbbe6b68b3b1897055c766ef05115f00234137`,
the grader's tested-through version) and **3.12.0**
(`dcafcf10435a9218ec9632f82dca246581224269`). Read its AGENTS.md. Exercised the
3.12.0 inventory builder with a synthetic API response: it emitted
`metric_references: ["visits"]` in `to_full_dict()` and `"visits"` in
`to_dict()`, preserving the canonical definition in both. Source authorities:
[shortening](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/inventory/utils.py#L133),
[calculated metric export](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/inventory/calculated_metrics.py#L194),
[segment export](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/inventory/segments.py#L190).
The JSON writer explicitly supports records-only fallbacks. Version constants
are unchanged; this is focused source verification, not full certification of
every exporter version or live tenant behavior.

## Pipeline investigation and deferred findings

- **Selection/detection/history/trend:** loader -> platform dispatch -> history
  identity -> trend runner. Offset filename parsing still discards offsets
  (`input/loader.py:147`): the committed offset reproducer selects 09:00+09
  after 01:00Z and reports a false -11 trend/exit 2. Deferred to a timestamp
  patch shared across selection/trend, with filename compatibility tests.
  Normal CLI trend regrades all points under one rubric/config; no additional
  mixed-version comparison bug established. History matches platform + instance.
- **Adapters/evidence:** current aliases preserve dimension/variable namespaces;
  no metric/dimension suffix identity was inferred. New tests exercise empty,
  malformed, nested and partial reference evidence. Malformed optional AA
  definitions remain empty and yield no references per #62. Conflicting duplicate
  segment IDs still choose the last graph row (`rules/checks/segments.py:101`):
  rerun gives 100/A versus 97/A. Deferred: define conflict diagnostics across all
  inventories, including legitimate derived-field echoes, rather than imposing
  an isolated graph merge that manufactures evidence.
- **Rules/applicability/wording:** the existing rules reproducer still shows
  truthy malformed governance flags giving 100/A rather than 78/C+ and string
  persistence `enabled` producing an unsupported finding (98 versus 100).
  `governance.py:289`, `schema_hygiene.py:375`, `attribution.py:164` need a
  separate consistent boolean evidence contract. The Time Decay description
  counterexample still gives 90/A-minus versus 100/A; vocabulary completeness
  is separate from reference identity. Custom governance dates still produce
  0/F versus 100/A for equivalent timestamps (`governance.py:300`); include
  these in the timestamp follow-up. Exact minimal inputs/commands and evidence
  remain in [original audit and reproducers](2026-09-07-correctness-audit.md), rerun against this baseline.
- **Counting/scoring/suppression:** traced effective-rule inventory into both
  execution and denominator. Fired rule IDs count once, component totals include
  all five inventories, excluded platform rules and whole-rule suppressions
  leave the denominator. Category order and malformed scopes pass #61's CLI
  regressions. Empty effective categories score 100 by the documented rubric
  contract; changing this needs policy/version discussion. Strict/pragmatic
  penalties need not be monotonic; no such contract exists. No thresholds,
  weights, grades, recalibration or new rules are proposed.
- **Output/CLI:** one Report feeds JSON/HTML, grades determine exit 2, and input
  errors precede publication. New resource-error tests assert absent reports.
  Existing output tests cover staging and contextual publication failure. The
  final rename sequence is not a multi-file filesystem transaction; a second
  rename failure can leave the first destination replaced while returning an
  error. Deferred output-atomicity design, not a claim of rollback guarantees.
- **Disabled/deleted and partial inventories:** Adobe documents `isDeleted`,
  but the normalized resolver has no availability-state contract. Hidden is
  not proven deleted; missing export rows are not proven live absence. No new
  penalty/exclusion or runtime assertion is justified here. Cycle and persistence
  runtime wording remains a prior documented evidence limitation.

Zero private entries are admitted for calibration. Compatibility is not evidence
for threshold correctness. No private IDs, snapshots or reports belong in this PR.

## Validation

`tests/test_cja_reference_evidence.py` checks independently specified literal
scores/exits, full/canonical/records equivalence under both packs, cycle aliases,
namespace/path collisions, partial/unknown definitions, malformed evidence,
deduplication/permutations, repeat execution, and CLI JSON/HTML/resource failures.
Against a scratch package containing main's CJA adapter, **30 fail / 16 pass**;
the passing opposite cases protect supported behavior. The existing ordering
assertions now expect sorted references. Public generated scores remain CJA
100/47 and AA 100/55; only reference row order changes in the messy CJA HTML.

Full candidate suite: **1,221 passed**, coverage **99.02%** (required 99%).
Ruff, version identity and diff whitespace checks pass. All four required
fixture/example generators ran; public grades above remain unchanged.

The manifest-listed private cohort contains 108 snapshots (100 CJA, 8 AA).
Baseline and candidate each produced 216 successful reports across both packs;
candidate renders were repeatable. 66 reports changed, 50 changed score
(40 increases, 10 decreases). Rule-presence deltas across pack/snapshot reports:
SCH-002 added in 10 and removed in 30; CALC-002 removed in 38; CALC-014 removed
in 6 as complete identities distinguish reference sets formerly collapsed by
abbreviations. AA reports are unchanged. These are aggregate compatibility
effects, not human-validated customer grading outcomes or calibration evidence.
The private comparison artifacts stay outside Git.

Local CE code review completed within Codex with independent correctness,
adversarial, testing and project-standards lenses: no actionable findings.
Both suggested test gaps (AST-shaped comparison literals and multi-item
CSV/list equivalence) were added and reviewed in a final follow-up. No external
model provider received repository content. Installed-wheel CLI checks also
passed outside the checkout on Python 3.12 and 3.14 for all four original
counterexamples. No version bump, tag, release or merge was performed.

## P2 deferred output reproduction: second publication rename fails

`src/sdr_grader/cli/output.py:126` publishes staged destinations sequentially.
Injecting an I/O failure on the second rename returns exit 1 with the correct
failure diagnostic, but leaves the new HTML and no JSON. The successful HTML's
score is not itself miscomputed; the requested report set is incomplete.
This is separate from CJA evidence normalization and requires an explicit
rollback or publication-manifest contract (including existing outputs and
rollback failures), so no isolated filesystem patch is included here.

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from sdr_grader.cli.main import main
from sdr_grader.cli import output
with TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'snapshot.json'
    source.write_text('{"metadata":{"Data View ID":"dv1"},"metrics":[],"dimensions":[]}')
    original, calls = output.os.replace, []
    def fail_second(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError('synthetic second rename failure')
        return original(src, dst)
    with patch.object(output.os, 'replace', fail_second):
        code = main([str(source), '--output', str(root/'report.html'),
                     '--json', str(root/'report.json'), '--quiet'])
    print(code, (root/'report.html').exists(), (root/'report.json').exists())
PY
```

Actual: `1 True False`. Desired under an all-or-nothing report-set contract:
`1 False False` for fresh destinations; existing reports must be restored.
The existing implementation only promises staged writes and a failure exit,
so classify stronger atomicity as requested resilience work, not a regression
introduced by this patch. Future tests must inject second-publication and
rollback failures, rather than merely failures during staging.

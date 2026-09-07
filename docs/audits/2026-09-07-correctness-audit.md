# SDR grader correctness audit — 2026-09-07

Reviewed the entire current checkout on `main`, commit `366b0834301c69b5a69a493a8bd77328710188bf` (sdr-grader 1.2.7), not merely a diff. **Nine grading defects and one additional malformed-input defect are confirmed.** The audit itself left the checkout unchanged. This PR now addresses findings **5, 6, and 10** with localized production fixes and CLI regression tests. The remaining findings are deferred to separate iterations to keep this patch focused. All actual/expected results below describe the audited baseline, not a claim that these three defects remain in the patched branch.

**Patch validation:** `tests/test_patch_grading_boundaries.py` checks category-order invariance, malformed suppression scopes, and contextual AA errors through the real CLI. The committed `observed-output.txt` is historical baseline evidence; rerunning the scripts on the patched branch is expected to differ for findings 5, 6, and 10.

The main risks are false unresolved-reference findings on normal CJA exporter output, silently discarded reference evidence, and score/CI changes caused by representation or ordering rather than implementation quality. Severity below ranks impact and likelihood: P1 high, P2 moderate, P3 low. No P0 issue was confirmed.

Run all counterexamples from the repository root:

```bash
.venv/bin/python docs/audits/2026-09-07-reproductions/reproduce.py
```

[Executable reproducer](2026-09-07-reproductions/reproduce.py) invokes five self-contained scripts. [Captured results](2026-09-07-reproductions/observed-output.txt) include scores, grades, findings, and exit codes. Scripts write synthetic fixtures and reports only under `/tmp`; they need the checkout's existing Python environment, not upstream credentials or live Adobe access. They demonstrate current behavior; the regression expectations below specify the desired behavior independently.

## Confirmed grading defects

### 1. P1 — Supported CJA exporter IDs falsely flag a valid calculated metric

**Code:** [adapters/cja.py:315](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/adapters/cja.py#L315), especially reference collection at lines 318–319. The canonical definition is parsed at line 310 but is not used to recover references.

**Minimal input:**

```json
{
  "metadata": {"Data View ID": "dv1", "Tool Version": "3.11.7"},
  "metrics": [], "dimensions": [],
  "calculated_metrics": {"metrics": [{
    "id": "cm1", "name": "Session count", "description": "Counts sessions",
    "metric_references": ["visits"],
    "definition_json": "{\"func\":\"calc-metric\",\"formula\":{\"func\":\"metric\",\"name\":\"metrics/visits\"}}"
  }]}
}
```

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/adapters_repro.py` creates `/tmp/adapter-healthy-exported.json` and runs the CLI. Direct command:

```bash
.venv/bin/python -m sdr_grader /tmp/adapter-healthy-exported.json \
  --fail-below C --output /tmp/healthy.html --json /tmp/healthy.json
```

**Actual:** SCH-002 and CALC-002 falsely report unresolved references; **71/C−, exit 2**. Changing only the summary list to `["metrics/visits"]` gives **78/C+, exit 0**. GOV-001/GOV-003 fire in both variants and account for the remaining baseline penalties.

**Expected:** no unresolved-reference finding for Sessions; **78/C+, exit 0** under the otherwise unchanged strict 2.0 pack. Adobe identifies `metrics/visits` as Sessions in the current [CJA Metrics API](https://developer.adobe.com/cja-apis/docs/endpoints/metrics/).

**Root cause and upstream contract:** the upstream exporter intentionally shortens reference IDs. Its actual inventory builder was invoked with the API definition above and produced `metric_references: ["visits"]`, while preserving the canonical definition. This is present in the grader's tested-through exporter **v3.11.7**, commit `98dbbe6b68b3b1897055c766ef05115f00234137`, and the inspected **3.12.0** checkout, commit `dcafcf10435a9218ec9632f82dca246581224269`. See upstream [reference shortening](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/inventory/utils.py#L133) and [calculated-metric extraction](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/inventory/calculated_metrics.py#L662). These exact tagged sources were verified with local `git show`; web retrieval of the upstream files returned cache misses. This is not an inference from fabricated canonical-reference fixtures.

**Smallest fix:** extract canonical references from typed definition nodes. Where definitions are unavailable, resolve shortened IDs only when namespace-aware evidence establishes an unambiguous identity; do not globally equate suffixes. **Regression:** upstream-shaped Sessions fixture, unresolved metric fixture, and a metric/dimension suffix collision; assert adapter references, rule IDs, score, JSON/HTML, and CLI exit.

### 2. P2 — Records-only CJA exports discard reference evidence and pass a failing gate

**Code:** [adapters/cja.py:651](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/adapters/cja.py#L651), particularly the JSON parsing failure returning an empty list at line 662. The segment path additionally omits the tabular `segment_references` alias at [cja.py:423](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/adapters/cja.py#L423).

**Minimal input:** use finding 1's snapshot, set the definition's name to `metrics/deleted`, then compare `"metric_references": ["deleted"]` with `"metric_references": "deleted"`. No matching metric is exported. All other evidence remains identical.

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/adapters_repro.py`, cases `broken-full` and `broken-records`; the script writes `/tmp/adapter-broken-full.json` and `/tmp/adapter-broken-records.json`. Grade either using the command in finding 1 with its input path and `--fail-below C`.

**Actual:** full representation produces SCH-002/CALC-002, **71/C−, exit 2**. Records-only representation normalizes to `references=[]`, omits both findings, and gives **78/C+, exit 0**.

**Expected:** equivalent supported export representations must retain the same reference evidence and produce equivalent findings, score, and exit. Under the current unresolved-reference policy, the records case should also produce **71/C−, exit 2**. The snapshot establishes an unresolved reference; it does not independently prove that the live Adobe implementation is broken.

**Root cause and contract:** upstream [CalculatedMetricSummary.to_dict](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/inventory/calculated_metrics.py#L194) joins references into comma-separated text; the [JSON writer fallback](https://github.com/brian-a-au/cja_auto_sdr/blob/98dbbe6b68b3b1897055c766ef05115f00234137/src/cja_auto_sdr/output/sdr/__init__.py#L565) emits these records when full inventory objects are absent. Both upstream versions noted in finding 1 were inspected, and current builder `to_dict()`/`to_full_dict()` were exercised. The grader explicitly accepts records-only sections but its reference parser accepts only native or JSON-encoded arrays. The intact definition is ignored as a reference fallback.

**Smallest fix:** derive references from available definitions and support exporter tabular representations/aliases where needed. **Regression:** full versus records-only equality for valid references, unresolved references, and segment cycles. This is separate from finding 1: shortened list IDs cause false positives, whereas discarded text references cause false negatives.

### 3. P2 — Truthiness converts malformed evidence into both healthy and unhealthy claims

**Code:** [governance.py:289](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/governance.py#L289) and [governance.py:295](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/governance.py#L295); CJA settings repeat the issue at [schema_hygiene.py:375](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/schema_hygiene.py#L375) and [attribution.py:164](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/attribution.py#L164).

**Minimal governance input:**

```json
{"report_suite":{"rsid":"x"},"metrics":[],"dimensions":[],
 "metadata":{"history_present":"false","sdr_doc_present":"false"}}
```

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/rules_repro.py` and `.venv/bin/python docs/audits/2026-09-07-reproductions/governance_dates_repro.py`.

**Actual:** strings `"false"` or nonempty objects such as `{"present":false}` suppress GOV-001/GOV-003: **100/A, --fail-below A exit 0**. JSON boolean `false` produces both findings: **78/C+, exit 2**. Custom rule parameter overrides also use `bool(value)`.

The inverse failure occurs for CJA settings. With affirmative governance flags, put this one dimension into a minimal CJA snapshot:

```json
{"id":"variables/x","name":"X","description":"Dimension","tags":["business"],
 "persistenceSetting":{"enabled":"false",
   "allocationModel":{"expiration":{"granularity":"day","numPeriods":91}}}}
```

**Actual:** string `"false"` causes SCH-007 and **98/A**; boolean `false` yields **100/A**. The finding asserts active over-cap persistence even though the enable value is malformed.

**Expected:** malformed values must not establish either affirmative history/documentation or an active platform setting. Reject them, or parse only explicitly supported boolean representations; preserve unknown separately. A malformed string/object is not proof of the real implementation's state. If textual booleans are supported, `"false"` must normalize to false.

**Root cause/contract:** dictionary shape checks followed by Python truthiness, rather than semantic flag validation. The normalized model distinguishes absent signals from explicit false, the adapter guide requires malformed-input handling, and the rubric audit describes governance as explicit evidence. The choice to penalize genuinely absent governance evidence is a separate policy issue.

**Smallest fix:** shared strict optional-boolean normalization at the input boundary and rubric validation for override flags; validate nested setting enable fields before rules run. **Regression:** true/false, absent/null, zero, textual booleans, lists, objects, and conflicting aliases, including JSON-encoded settings. Assert malformed evidence never silently changes a gate into a pass or fabricates an active-setting finding.

### 4. P2 — Filename timezone offsets reverse chronology, trends, and the latest gate result

**Code:** [input/loader.py:29](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/input/loader.py#L29) and [loader.py:152](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/input/loader.py#L152).

**Minimal directory:**

```text
snapshot_2026-04-25T09:00:00+09:00.json
snapshot_2026-04-25T01:00:00Z.json
```

Each contains `{"metadata":{"Data View ID":"dv_x","Generation Timestamp":"<filename timestamp>","sdr_doc_present":false},"metrics":[],"dimensions":[]}`; use `sdr_doc_present:true` in the second. The first instant is 00:00Z and scores 89/B+; the second is 01:00Z and scores 100/A. Directory/trend history evidence is available in both.

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/offset_trend_repro.py`. It builds the directory, calls latest selection and trend generation, and invokes `--trend --fail-below A`. Generated HTML is written to `/tmp/audit-offset-trend.html` when the reproducer runs.

**Actual:** latest selection chooses the older `09:00+09:00` file. Trend treats it as 09:00Z, reports **−11 points**, ends at **89/B+**, and exits **2**. The embedded report timestamp is correctly 00:00Z, so the trend disagrees with its own report's date.

**Expected:** improvement **+11**, latest **100/A**, exit **0**. [TREND_REPORTS.md](../../docs/TREND_REPORTS.md#L29) recommends ISO-8601 timestamps. Numeric offset semantics are independently defined in [RFC 3339 §4.2](https://www.rfc-editor.org/rfc/rfc3339#section-4.2).

**Root cause:** regex extracts local clock fields but ignores the offset; construction forcibly attaches UTC. **Smallest fix:** parse and normalize the complete timestamp, including offset and fractional seconds; reject unsupported suffixes instead of accepting only a misleading prefix. **Regression:** the two-file case through latest selection, `--at`, trend order/delta, and threshold exit; include equivalent UTC filename forms and offset-crossing dates.

### 5. P2 — Reordering category weights changes the score, letter grade, and exit code

**Code:** [core/grade_calc.py:88](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/core/grade_calc.py#L88) through line 91; suppression normalization also uses an order-sensitive sum at [suppression.py:234](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/suppression.py#L234).

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/scoring_repro.py`. This writes a minimal AA snapshot with one undescribed dimension and two five-rule custom packs `/tmp/sdr-audit/abc` and `/tmp/sdr-audit/cba`. All rules use the existing `missing_descriptions` check; no test-only registration or monkeypatch is involved.

The packs differ only in YAML mapping order:

```yaml
category_weights: {a: 0.1, b: 0.2, c: 0.7}
# versus
category_weights: {c: 0.7, b: 0.2, a: 0.1}
```

Shared severity weights: critical 19, high 9, medium 1, low 1. Category a contains a passing critical rule and failing low rule (95%); b contains a passing medium rule (100%); c contains a passing high rule and failing low rule (90%). A threshold 1 makes a rule pass; threshold 0 makes it fail for the supplied undescribed dimension. Both use the bundled grade scale.

```bash
.venv/bin/python -m sdr_grader /tmp/sdr-audit/minimal.json \
  --rubric /tmp/sdr-audit/abc --fail-below A --output /tmp/order-abc.html
# Repeat with --rubric /tmp/sdr-audit/cba and a separate output path.
```

**Actual:** abc gives **92/A−, exit 2**; cba gives **93/A, exit 0**, with identical category percentages and failures.

**Expected:** the same result for the same weight mapping. The exact average is `95×0.1 + 100×0.2 + 90×0.7 = 92.5`. Applying the implementation's stated Python round policy gives **92/A−, exit 2** in both. A different explicit tie policy could choose 93 in both; order cannot decide it.

**Root cause:** sequential binary-float summation changes the denominator from 1.0 to 0.9999999999999999 and crosses a rounding boundary. This is independent of subjective severity/weight selection and violates semantic input-order independence.

**Smallest fix:** use stable summation consistently in scoring and weight normalization; use decimal/rational arithmetic if exact decimal tie behavior is the public contract. **Regression:** permutations of the same category mapping, half-point boundaries, suppression normalization, final JSON/HTML grade, and `--fail-below`. Preserve the separately documented policy of rounding category subtotals before the overall average.

### 6. P2 — A malformed component suppression silently becomes a whole-rule suppression

**Code:** [rules/suppression.py:97](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/suppression.py#L97), before the list check at line 98.

**Minimal config:**

```yaml
suppress:
  - rule: a-fail
    components: false
```

Use finding 5's minimal snapshot and abc pack. **Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/scoring_repro.py`; its suppression cases also test `components: 0`, `{}`, and `""`.

**Actual:** each invalid value becomes `[]` via `entry.get("components") or []`. An empty component list denotes full suppression, so `a-fail` disappears: **92/A− becomes 93/A**, and `--fail-below A` changes **2 to 0**.

**Expected:** **rubric validation exit 3, no published report**, because the [project config contract](../../docs/PROJECT_CONFIG.md#L43) requires a list of strings and specifies loud structural failures. This does not depend on implementing currently unsupported component-level suppressions.

**Root cause:** defaulting happens before type validation and widens scope. **Smallest fix:** distinguish an absent field from a present value, then validate list and element types before constructing `SuppressedRule`. **Regression:** all four falsy wrong types, non-string list items, omitted components, explicit empty list under the chosen policy, and a valid nonempty component list; assert malformed configs cannot remove findings or publish output.

### 7. P2 — ATTR-004 penalizes a description that names the model and explains its purpose

**Code:** [attribution.py:143](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/attribution.py#L143) and [attribution.py:170](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/attribution.py#L170).

**Minimal input:** CJA snapshot with empty dimensions, affirmative governance metadata, and this one metric:

```json
{"id":"metrics/revenue","name":"Revenue","tags":["business"],
 "description":"Time decay with a 7-day half-life, chosen to favor recent touchpoints.",
 "attributionSetting":{"enabled":true,"attributionModel":{
   "func":"allocation-timeDecay","context":"visitors",
   "halfLifeNumPeriods":7,"halfLifeGranularity":"day"}}}
```

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/rules_repro.py`.

**Actual:** ATTR-004 reports an undocumented override, **90/A−**. Merely inserting the word `attribution` after `Time decay` produces **100/A**.

**Expected:** no documentation finding, **100/A**. The existing [strict remediation](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/packs/strict/attribution.yaml#L48) asks for the model and why it was chosen; this sentence supplies both plus its parameter. Adobe's [CJA attribution documentation](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/attribution), updated June 5, 2026, documents Time Decay and its default seven-day half-life. This finding concerns adherence to the chosen rubric, not whether descriptions should be graded at all.

**Root cause:** the acknowledgement regex recognizes selected models but omits Time Decay and other official names, including Algorithmic and Same Touch. **Smallest fix:** recognize official model display names/aliases, preferably the configured model specifically, without requiring a magic generic keyword. **Regression:** sufficient descriptions for each supported attribution model, plus genuinely missing explanations. Do not treat a bare generic word such as “model” as independently proving an adequate rationale.

### 8. P2 — Conflicting duplicate segment IDs make cycle findings depend on row order

**Code:** [rules/checks/segments.py:101](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/segments.py#L101); the adapters admit both records without checking conflicting identity.

**Minimal input:** AA snapshot with empty metrics/dimensions, both governance flags true, and:

```json
"segments": [
  {"id":"s1","name":"S1","description":"Cycle",
   "definition":{"func":"segment-ref","id":"s1"}},
  {"id":"s1","name":"S1b","description":"No cycle",
   "definition":{"func":"container","context":"hits","pred":{"func":"true"}}}
]
```

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/rules_repro.py`, last two cases.

**Actual:** this order gives **100/A, no findings**. Reverse the rows: **97/A, SEG-004**.

**Expected:** an invalid/ambiguous evidence diagnostic independent of order. Neither row is proven authoritative; the finding is not that the live segment necessarily contains a cycle. A stable identifier cannot silently select contradictory definitions according to input order.

**Root cause:** graph dictionary comprehension overwrites earlier adjacency for the same ID. **Smallest fix:** reject conflicting same-kind duplicate IDs before grading; optionally deduplicate truly identical rows. **Regression:** all permutations of conflicting rows must produce the same contextual rejection. If ambiguity is deliberately supported, preserve all relevant evidence and expose the ambiguity explicitly rather than inventing one authoritative graph.

### 9. P2 — Equivalent ISO timestamps silently disable custom governance checks

**Code:** [rules/checks/governance.py:300](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/rules/checks/governance.py#L300). Applies to registered **custom-pack GOV-002/GOV-006**, not bundled 2.0 checks.

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/governance_dates_repro.py`. It constructs one-rule rubrics using real registered checks, high severity, category weight 1, and the bundled grade scale.

For `snapshot_age`, use `reference_date: "2026-04-25T00:00:00Z"`, `max_age_days: 90`, and compare these equivalent snapshot metadata timestamps:

```text
2026-01-01T00:00:00Z
2026-01-01T00:00:00+00:00
2026-01-01T00:00:00.000Z
```

For `doc_drift`, put the same timestamp in the sole dimension's `modified_at`, use `last_sdr_update_at: "2025-01-01T00:00:00Z"`, threshold 0.2.

**Actual:** the first spelling fires each check, **0/F**; the latter spellings yield no finding and **100/A**. **Expected:** identical instants produce identical findings and grades: **0/F** in all three cases. The checks document ISO date inputs; numeric offsets and fractional seconds are valid [RFC 3339 §5.6](https://www.rfc-editor.org/rfc/rfc3339#section-5.6) timestamp forms.

**Root cause:** the governance-only parser accepts only three `strptime` formats; failed parsing becomes a no-op counted as a pass. The adapters preserve these timestamps and the shared report parser already understands them. [core/timeparse.py:9](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/core/timeparse.py#L9) explicitly acknowledges this deferred mismatch. A documented deferral explains its history but does not make equivalent evidence yield a correct grade.

**Smallest fix:** reuse `core.timeparse.parse_timestamp`. **Regression:** equivalent Z/offset/fractional timestamps for both checks, including changes across UTC date boundaries, and invalid dates that remain unknown rather than healthy proof.

## Additional confirmed robustness defect

### 10. P3 — Malformed AA calculated-metric definition raises an uncaught TypeError

**Code:** [adapters/aa.py:227](https://github.com/brian-a-au/sdr-grader/blob/366b0834301c69b5a69a493a8bd77328710188bf/src/sdr_grader/adapters/aa.py#L227).

```python
from sdr_grader.adapters.aa import adapt
adapt({"report_suite":{"rsid":"rs1"},"metrics":[],"dimensions":[],
       "calculated_metrics":[{"id":"cm1","definition":7}]})
```

**Reproduce:** `.venv/bin/python docs/audits/2026-09-07-reproductions/adapters_repro.py`, final case. The complete existing test suite independently found the same defect in `test_adapter_survives_mutated_fixture`, AA messy fixture, seed 381, mutation `replace_truthy_int` at `calculated_metrics[1].definition`.

**Actual:** `TypeError: 'int' object is not iterable`; no score is produced. **Expected:** contextual `InvalidSnapshotError`, handled by the CLI's normal invalid-input path, per [ADAPTER_GUIDE.md](../../docs/ADAPTER_GUIDE.md#L56).

**Root cause:** a non-dictionary definition yields `formula={}`, which passes the first condition before `set(definition)` executes. **Smallest fix:** validate definition shape before inspecting keys. **Regression:** numeric/boolean/list definitions and normal definition objects. This is a robustness issue, not a demonstrated false grading result; it is separated accordingly.

## Unresolved questions and calibration concerns

- **Missing evidence and empty implementations:** optional inventories normalize to empty collections, many checks no-op, and categories with no effective rules receive 100%. The latter is explicitly documented in `RUBRIC_FORMAT.md` under effective-rule safety. An empty implementation with affirmative governance flags can score A/100. This is a documented scoring limitation and incomplete-evidence design concern, not a newly invented arithmetic defect. Distinguishing pass, not applicable, unavailable, and invalid evidence would require an explicit policy/model decision.
- **Unresolved does not necessarily mean deleted:** absent inventory rows can reflect partial exports or permissions. The counterexamples establish what supplied evidence can resolve, not the live Adobe state. Completeness/pagination status needs a clearer supported contract before confidently diagnosing live breakage.
- **Governance prose overclaims:** a single snapshot cannot prove that documentation, history, compliance trails, or diff capability do not exist elsewhere. Current default absence penalties are explicit policy; report wording should stay at “not supplied/detected in this input.”
- **CJA/AA nesting units:** upstream CJA traversal depth and AA container-only depth can differ (one container plus five nested predicate wrappers yielded 6 versus 1). The normalization difference is demonstrated, but the intended cross-platform rubric counting unit is insufficiently explicit to declare which score is correct.
- **GOV-003 supplementary contract:** `RUBRIC_AUDIT.md` says documented supplementary input can establish SDR existence, but `_signal_present` never reads supplementary data. No precise GOV-003 supplementary schema was found. GOV-006's last-update schema does not by itself settle this; clarify the contract before calling it a supported-input implementation defect.
- **AA coverage narrative is outdated:** Adobe now documents allocation and expiration via Analytics **2.0** `expansion=attributionModel`. Therefore “only legacy 1.4 can supply this” is too broad. This does not establish that aa_auto_sdr **1.21.10**, the grader's tested-through exporter, requests or exports it, or that a bundled rule must automatically be added. See the current [Adobe dimension attribution API](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/dimensions/attmodel).
- **Other unsupported runtime claims:** the persistence finding asserts silent query-time clamping, and cycle findings assert particular platform runtime consequences. The inspected primary documentation did not establish those mechanisms; the snapshot alone cannot. Treat these as wording/evidence concerns pending authoritative confirmation, rather than claiming a specific Adobe runtime bug.
- **Subjective rubric choices:** naming synonyms, mixed segment scopes, reference-set similarity, binary per-rule penalties, category weighting, and strict/pragmatic severity differences are policy choices. I did not require pragmatic grades to be monotonic relative to strict without an explicit policy contract.
- **Calibration:** the four requested audit/coverage/corpus documents correctly disclose zero admitted calibration entries. Compatibility testing of 108 private snapshots is not accuracy calibration. Thresholds and score/letter bands remain maintainer judgment. The optional bundled distribution is documented seed data; it should not be interpreted as independent population validation.

## Coverage and checks performed

- Searched for applicable `AGENTS.md` in the repository and parent directories; none found. Read root `CLAUDE.md` as the repository standards source. Read the sibling upstream `AGENTS.md` when inspecting its source. Reviewed all four requested context documents, adapter/rubric/project-config/trend contracts, prior correctness audit, both bundled packs, and relevant tests without treating their assertions as ground truth.
- Traced snapshot selection/detection, adapters and normalization, rule applicability/execution, suppression, severity denominators, category exclusions/rounding, report construction, JSON/HTML serialization, trend ordering/history identity, and threshold dispatch. Checks span built-ins, aliases, nested definitions, cycles, duplicates, missing/malformed signals, supplementary behavior, and custom packs.
- Full run: `.venv/bin/python -m pytest -q` — **1,142 passed, 1 failed, 25.52 seconds**. Failure is item 10. Focused passes additionally returned 212 adapter/input tests, 155 rule tests, 109 trend/CLI tests, and 132 independent validator tests; these overlap the full suite and are not additive coverage counts.
- Ran all synthetic counterexamples again through the consolidated reproducer. CLI cases publish HTML/JSON; output carries the incorrect grade rather than independently recomputing it. The CLI threshold comparison itself agrees with its supplied integer score; confirmed gate errors arise upstream. The offset trend also demonstrates a date disagreement between trend position and its underlying report timestamp.
- A separate reviewer independently reran and checked every grading candidate. No candidate in the final nine relies solely on test coverage or inspection. No independent cross-model peer was run; review passes shared the session model family. No production fixes, commits, external messages, or live Adobe mutations were made.
- No mixed-rubric-version defect was confirmed in normal CLI trend mode: it regrades every snapshot under the same supplied rubric/configuration. No additional grade-band or per-finding double-counting defect was established beyond the order-sensitive arithmetic above. Scoring counts a fired rule once even if it emits multiple findings; distinct overlapping rules are a rubric choice.

**Remaining blind spots:** no live tenant/API collection or private calibration corpus audit; no exhaustive proof for all upstream exporter versions, permission-filtered/partial inventories, pagination, deleted/disabled component states, every supplementary schema, or every custom rubric parameter combination. General byte-identical output was covered by existing tests, not exhaustively proven for every input permutation. Upstream tagged sources were available locally, but their GitHub web fetches failed. Public Adobe sources were checked on 2026-09-07; current API availability must not be retroactively attributed to older exporters.

## Actionable findings and verdict

Address 1–2 first: use real exporter fixtures and retain canonical reference evidence. Then fix boolean validation (3), timestamp ordering (4), score stability (5), and suppression scope validation (6). Correct the attribution vocabulary (7), duplicate-ID handling (8), and custom governance parser (9). Handle the isolated malformed-AA exception (10) alongside adapter validation.

**The audited baseline produced demonstrably false grades and CI outcomes.** Nine grading findings have minimal reproductions and independent validation; the additional test failure is a separate robustness defect. The audit is complete within the stated blind spots. This patch addresses findings 5, 6, and 10; the other validated issues remain follow-up work.

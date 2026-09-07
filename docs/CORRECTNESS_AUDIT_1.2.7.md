# Correctness evidence audit: 1.2.7

Reviewed the 1.2.6 source at `527fd76` before implementing this patch.
The audit followed input loading and platform detection through adapters,
normalized references, bundled and opt-in checks, scoring, suppression,
CLI exit codes, HTML rendering, and schema-1 JSON serialization. Findings
below are reproducible defects, not a claim that a customer's live
implementation is correct or broken.

## Confirmed defects and reproductions

All identifiers below are synthetic. Executable reproductions and opposite
cases live in `tests/test_aa_definition_evidence.py` and
`tests/test_correctness_evidence.py`.

### 1. AA comparison literals treated as component IDs

Minimal AA export: `report_suite: {rsid: synthetic}`, empty metrics,
dimension `variables/page`, and one segment with this predicate inside a
`func: container`, `context: hits` container:

```json
{"func":"streq","val":{"func":"attr","name":"variables/page"},"str":"metrics/documentation"}
```

Path: `aa.adapt` -> `_segment_from_record` ->
`_analyze_segment_definition` -> `Segment.references` -> SCH-002.
The old walker collected every prefix-looking string, including the literal,
and emitted **1 broken reference**. A literal naming another segment could
also manufacture a graph edge. Adobe explicitly distinguishes the `val`
reference from `str`, `list`, and `glob` literals in its
[segment definition contract](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/segments/definition).

The adapter now reads typed reference slots. Tests retain findings when the
actual attribute or event is absent and keep literal values out of the graph.
Legacy direct reference strings in `args` remain supported.

### 2. AA named formula operands lost

Minimal AA export: two calculated metrics with `definition.formula` set to
the following, replacing `metrics/revenue` with `metrics/orders` in the
second formula. Include all three metric IDs in the metrics inventory.

```json
{"func":"divide","col1":{"func":"metric","name":"metrics/revenue"},"col2":{"func":"metric","name":"metrics/visitors"}}
```

Path: `_calc_from_record` -> `_stringify_formula` and
`_extract_aa_calc_refs` -> CALC-015, CALC-002, and SCH-002.
Previously both formulas became `divide()` with empty reference lists:
distinct metrics received **1 repeated formula text** while genuinely
missing operands escaped reference checks. Adobe's
[calculated metrics examples](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/calculatedmetrics/)
use named operands and typed metric nodes; the upstream exporter preserves
the definition rather than converting it to positional `args`.

Structured formulas now retain their fields in deterministic JSON summaries,
and their typed input references are extracted. Outer definition filter
context is retained too. `segment-ref/id` is supported based on the
[adobeanalyticsr API-client implementation](https://rdrr.io/cran/adobeanalyticsr/src/R/cm_function.R);
the official pages reviewed do not fully specify that node. No prefix is
invented for saved segment IDs, and undocumented alternative node shapes
are not inferred. Tests distinguish equal/different formulas and filters,
and present/missing operands.

### 3. Missing definitions reported as duplicate segments

Minimal accepted CJA export:

```json
{"metadata":{"Data View ID":"dv_synthetic"},"metrics":[],"dimensions":[],"segments":[{"id":"s_a"},{"id":"s_b"}]}
```

Path: CJA `_parse_definition_json`, or AA `_segment_from_record`, supplies
`definition={}` for unavailable definitions -> SEG-006 serializes `{}` for
both -> **1 duplicate segment definition group**, high severity in strict.
The remediation recommended redirecting consumers and archiving segments
despite having observed neither definition. Adapter acceptance and sentinel
behavior establish the repository contract; no live-platform assumption is
needed. The check now requires a nonempty observed definition. Tests also
prove an actual duplicate pair remains detectable beside missing definitions.

### 4. Summary collisions override differing calculated-metric definitions

Minimal CJA export: two calculated metrics with the same `formula_summary`
(`Ratio calculation`) and different `definition_json` formulas, such as
`divide(col1=1,col2=10)` and `divide(col1=2,col2=10)`.
Path: CJA `_calc_metric_from_record` copies the summary -> CALC-015 lowercases
and groups text alone -> **1 repeated formula text** with archive guidance.
The upstream summary generator can abbreviate expressions and fall back to
operation descriptions; a summary is not the full formula contract.

CALC-015 now preserves case and groups equal summaries only when normalized
definitions also agree. Empty/dash-only summaries are not formula evidence.
Genuine repeated formulas remain detectable. This is conservative equality,
not semantic formula equivalence: metadata differences may prevent grouping,
and summary-only records still cannot establish live equivalence.

### 5. Namespace stripping manufactures cycles and hides missing targets

Minimal CJA export: metric `metrics/orders` and derived field
`variables/orders` with `component_references: ["metrics/orders"]`.
Path: CJA adaptation preserves the namespace -> SCH-008 `_bare_id` removes
it -> the reference becomes a false self-loop -> **1 derived-field reference
cycle**. Removing the metric also left SCH-009 silent because the dimension
suffix incorrectly satisfied the metric reference.

The adapter's existing contract explicitly distinguishes metric namespaces
from the established `dimensions/` and `variables/` equivalence. Resolution
now uses exact IDs and adapter-supplied aliases, preserving full suffix paths.
Tests cover genuine aliased cycles, noncycles, missing metrics, exact-ID
precedence, and unknown namespaces. The same alias mapping now lets SCH-005
recognize a deprecated dimension referenced under its established alias.
No customer occurrence of a metric/derived-field suffix collision was
established; the code/model defect has a synthetic reproduction.

### 6. Export absence described as proven live breakage

Minimal CJA export: calculated metric `cm_a` referencing `s_shared` while
the optional segment inventory is omitted; or a derived field referencing
an ID absent from this export. SCH-002/CALC-002 titles said **broken** while
their paragraphs cautioned that the live implementation might be valid.
SCH-009 asserted nonexistence in the data view and silent NULLs. Both packs'
remediation could recommend changing or retiring components before validation.

The optional-inventory adapter contract supplies no live completeness proof.
Titles now say **unresolved** and remediation calls for source-platform and
inventory verification first. Findings, configured severities, and penalties
remain: an unresolved ID is not assumed valid. Tests cover omitted, empty,
and populated inventories, both packs, CLI exit codes, deterministic reports,
and equal HTML/JSON evidence.

### 7. Evaluated-component counts omit graded inventories

An accepted export with one segment and one calculated metric, but no base
metrics/dimensions/derived fields, reported **0 components evaluated** in
JSON, the HTML summary, and the footer. Path: `grade` and `_build_tldr`
independently counted only the first three inventories, while the engine
also ran segment and calculated-metric rules. This contradicted the
`components_evaluated` description in `docs/JSON_OUTPUT.md` and understated
report coverage. Both paths now share the total across all five supplied
inventories. Synthetic AA/CJA tests assert a literal expected count of two;
aliases and omitted built-ins still add no inventory rows.

### 8. Saved-segment cycles discarded by an ID-prefix assumption

Minimal CJA inventory: `[{"id":"s_a","other_segment_references":["s_b"]},
{"id":"s_b","other_segment_references":["s_a"]}]`. The adapter preserves
both references, but SEG-004 previously discarded every edge without a
`segments/` prefix and returned no finding. Its contract is to detect cycles
in the exported segment reference graph, regardless of ID spelling.

SEG-004 now matches references against actual exported segment IDs. This
restores detection of contradictory cyclic input without inventing aliases
or declaring external references invalid. Sixteen adapter-through-rule cases
cover AA/CJA, both ID spellings, mutual cycles, self-cycles, valid chains,
and external references. This establishes a defect in graph inspection;
it does not establish that Adobe permits creating these cycles live.

## Validation and coverage limits

- Local baseline: 108 authorized private snapshots (100 CJA, 8 AA), all
  adapted and rendered with both packs: 216 successful reports. The patched
  run also produced 216 successful, repeatable reports. Customer contents,
  IDs, individual scores, and reports were kept outside Git and public logs.
- Eight snapshots contained equal summaries with differing known formulas.
  The patch removed CALC-015 in 12 pack/snapshot reports and changed those
  scores. No rule was newly triggered in the private comparison. Other
  changed private findings were the expected reference wording changes.
- No private snapshot had multiple unavailable segment definitions. Those
  cases, AA literal-prefix collisions, and namespace collision counterexamples
  are synthetic coverage, not evidence of customer incidence.
- None of the 108 entries is admitted for calibration. This is a compatibility
  and regression check, not threshold validation or a release attestation.
- Existing required-array validation, shape/resource limits, platform rule
  filtering, suppression denominators, full JSON evidence, HTML display caps,
  and scoring arithmetic were examined and retained. The standard generators
  keep the four public fixture scores at CJA 100/47 and AA 100/55.
- Adobe's current [persistence settings documentation](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/persistence)
  still specifies a maximum 90-day custom expiration. No defect in that
  configured limit was established. Runtime clamping/NULL behavior was not
  live-tested and should not be inferred from this audit.
- No additional universally available AA built-ins or CJA aliases were
  established. SCH-009's pre-existing broad built-in pattern remains a known
  coverage limitation; it was not expanded as a shortcut. Unknown IDs are
  not assumed valid. Customer-specific cross-data-view validity and export
  completeness require source-platform evidence, unavailable in this session.
- Naming, near-duplicate reference sets, container mixing, and documentation
  rules remain rubric heuristics. Their findings do not establish that a
  supported implementation cannot run. Opt-in attribution/ownership checks
  remain opt-in; absent metadata was not used to invent platform configuration.

Package/plugin version advances to 1.2.7; pack 2.0 and JSON schema 1 remain.
No thresholds, severity weights, category weights, or grade bands changed.
Run-level CI evidence is recorded on the PR. This session does not merge,
tag, or publish a release.

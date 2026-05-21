# Rubric audit — May 2026

A category-by-category audit of the 26 rules in the default `strict` and
`pragmatic` packs against Adobe's published documentation for CJA and AA,
plus the calibration evidence that already exists in
[`docs/threshold_calibration.md`](threshold_calibration.md).

The goal is to separate three buckets:

- **Solid.** Premise matches how the platform actually models the field,
  signal is meaningful, calibration agrees (or the rule is structural and
  doesn't need calibration). Keep as-is.
- **Weak.** Premise is defensible but the trigger is too coarse, the
  calibration is missing, or the practical signal-to-noise is thin.
  Demote to opt-in, tighten, or redesign.
- **Missing.** Adobe carries rich configuration that the current rubric
  doesn't grade at all. The opportunity cost of these gaps is often
  larger than the cost of any individual weak rule.

This is not a calibration report — `docs/threshold_calibration.md` is the
authority on whether a threshold is data-backed. This is a *premise*
audit: does the rule grade something the platform actually models, and
does the signal mean what the rule says it means?

## Methodology

For each rule:

1. Read the YAML entry (rationale, threshold, params) and the check
   function (what fields it reads, what it actually fires on).
2. Cross-reference with Adobe docs for the field(s) being graded. Cited
   URLs at the end of the document.
3. If calibration data exists in `threshold_calibration.md`, weigh it.
4. Disposition: **solid**, **weak**, or **redesign**.

## Schema hygiene (5 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| SCH-001 duplicate component names | **solid** | Adobe doesn't prevent name collisions within a type. Two metrics named "Revenue" with different IDs is a real bug that causes the classic "dashboards disagree" complaint. Structural rule, no calibration needed. |
| SCH-002 broken references | **solid** | Segments and calc metrics carry reference IDs; checking they resolve against `all_component_ids ∪ all_segment_ids ∪ calc_metric_ids` is correct. Critical for AA where the API can return zombie references after a deletion. |
| SCH-003 missing descriptions | **solid (calibrated)** | Threshold `0.35` set at p75 across 108 snapshots. Description fields exist on AA eVars/events and on CJA Data View components. Calibration explicit in `threshold_calibration.md`. |
| SCH-004 type-name mismatch | **weak — refine** | Premise (rate/percent name + integer type → silently broken) is real but the heuristic is too generic. `_RATE_NAME_RE` matches `rate\|pct\|percent\|ratio\|share` against the full name string — this catches "Currency Conversion Rate" (which is a decimal correctly) and misses metrics named "ConversionFactor" (which might be a broken integer). Either narrow the regex to word-boundary common-suffix patterns (`_rate$\|_pct$\|_ratio$`) or expand the data-type whitelist to recognize Adobe's actual type names: AA events are `counter` / `numeric` / `currency` / `numeric_no_subrelations` — `counter` is the integer-equivalent, the others are decimal. The current rule's `_INTEGER_TYPES = {"integer", "int", "long"}` won't recognize AA's `counter` and won't fire on the actual integer-rate case. |
| SCH-005 deprecated components still in use | **weak — refine regex** | Premise is real — Adobe doesn't enforce deprecation lifecycle. The regex `\b(deprecated\|legacy\|old\|deleteme\|do_not_use\|v0\|tmp\|temp)\b` is too greedy: `\bold\b` matches "Order Total" (Order**T**otal has no word boundary issue but "Holdovers" or "old_customer_segment" would match), `tmp` and `temp` are weak signals (matches "temperature"), `v0` matches `eVar0`. Drop `old`, `tmp`, `temp`, `v0` from the default set — keep them as opt-in via `params`. Keep `deprecated\|legacy\|deleteme\|do_not_use`. |

## Naming consistency (4 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| NAME-001 prefix consistency | **weak — depends on tag convention** | Default `target: dimensions, tag_filter: custom`. Will fire only on dimensions tagged "custom". Adobe doesn't enforce a "custom" tag convention; most tenants won't have it. The rule effectively no-ops on most snapshots. Either drop the `tag_filter` default (grade ALL dimensions) and accept some platform-default-prefix noise, or document that this rule requires the operator to tag their custom components. The latter is closer to how it's framed in `_meta.yaml` (consultant-grade rules assume hygienic tagging). |
| NAME-002 ID pattern | **solid** | AA IDs are constrained system-assigned strings (`evar1`, `event23`); CJA dimension IDs are SchemaPath strings (`variables/evar5`, `metrics/m_orders`). The default pattern `^[A-Za-z0-9_/.\-]+$` accepts both correctly. Real-world bugs from spaces in IDs DO occur (cja_auto_sdr has handled at least one such report). Structural, no calibration needed. |
| NAME-003 casing consistency | **weak — same `tag_filter: custom` issue as NAME-001** | The casing classifier itself is solid (camelCase / PascalCase / snake_case / kebab-case / SCREAMING_SNAKE / Title Case / lowercase phrase). The constraint that it only grades `custom`-tagged dimensions makes it a no-op in practice. |
| NAME-004 semantic synonym mixing | **solid — but expandable** | Synonym groups are platform-agnostic linguistic patterns (`user/visitor`, `page/screen`, `session/visit`). The signal is real: mixed vocabulary fragments downstream tooling. Worth adding Adobe-domain groups: `revenue/sales`, `cart/basket`, `order/transaction`, `purchase/checkout`. (An earlier draft of this audit suggested `event/conversion` — dropped on closer reading because "event" is an AA platform primitive that legitimately coexists with "conversion" in component names; the pair would false-fire on every AA tenant.) |

## Segment complexity (5 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| SEG-002 container mixing | **solid** | CJA uses event/session/person containers; AA uses Hit/Visit/Visitor. The adapter walks segment definitions and identifies container `context` values. The premise — mixing containers within one segment is genuinely confusing — is consistent with Adobe's own guidance for segment composition. |
| SEG-004 circular segment references | **solid** | Adobe's segment evaluator handles cycles but the population semantics are inconsistent between UI and export. A real bug to flag. Structural, no calibration needed. |
| SEG-005 missing descriptions | **solid (calibrated)** | Threshold `0.95` — calibration explicit: ~90% of corpus tenants are at 100% missing. Rule deliberately fires only on the worst cases. Severity demoted to low post-calibration. |
| SEG-006 duplicate definitions | **solid** | Canonical JSON serialization of `s.definition` as the dedup key. Adobe ships duplicate-detection in its own UI but not at the API level; rule fills a real gap. |
| SEG-007 nesting depth | **solid (calibrated)** | Threshold p75 = 5. Calibration explicit. |

## Calc metrics (5 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| CALC-001 missing descriptions | **solid (calibrated)** | Threshold 0.95; severity low post-calibration. Calibration explicit: "nearly every real tenant has 100% calc metrics missing descriptions." |
| CALC-002 broken formula refs | **solid** | Same logic as SCH-002 but scoped to calc metric formulas. Real bug class. |
| CALC-003 formula complexity | **solid (calibrated)** | Threshold 22 = p90. Complexity score is computed by `cja_auto_sdr` from the parsed formula AST; matches the upstream tool's own complexity metric. |
| CALC-014 near-duplicates (Jaccard ≥ 0.85) | **solid** | Reference-set Jaccard over calc metric references is a principled near-dup signal. Severity high reflects that this catches the "Revenue (v1)" vs "Revenue (final)" vs "Revenue (canonical)" anti-pattern. |
| CALC-015 identical formula text | **solid** | Different from CALC-014 — same formula bytes, different IDs/names. A copy-paste-and-forget smell. |

## Attribution (3 rules)

The full analysis lives in the conversation transcript that produced this
audit; summary here.

| Rule | Disposition | Notes |
|------|-------------|-------|
| ATTR-001 silent last-touch default | **weak — premise partly right, trigger too coarse** | Adobe's docs confirm Last Touch IS the platform default when no model is specified. So the premise is real. But the trigger flags every revenue-named calc metric without baked-in attribution, which is most of them. Most calc metrics are simple ratios where attribution is correctly set at the panel level in Workspace. Effect: the rule fires on the common case, not the actually-risky subset (executive-dashboard calc metrics where attribution should be baked in). Recommendation: demote to opt-in, require an additional signal (e.g. metric is referenced from a Workspace project export passed via `--extra-input`). |
| ATTR-002 calc metrics lacking explicit attribution > 30% | **weak — uncalibrated, almost certainly degenerate** | Threshold 0.30 is a guess, not measured. Likely fires on every tenant. Calibration support added in `scripts/calibrate_thresholds.py`; the May 2026 calibration commit (next time corpus runs) will surface the actual distribution. Predicted outcome: distribution sits at p25 = 0.85+, making the rule indiscriminate. |
| ATTR-003 same-refs different-attribution inconsistency | **solid in principle, rare in practice** | When fired, signal is genuine. Conflict requires ≥2 calc metrics with same input refs AND ≥2 distinct non-None attribution models — rare prerequisite (most calc metrics have None). Keep as-is; expect it to rarely fire. |

## Governance (4 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| GOV-001 no snapshot history | **defensible** | Extrinsic signal — the snapshot itself can't carry "is there a directory of older snapshots". Rule fires by default and is silenced by `history_present=true` from the loader / CI when evidence exists. Functions more like a nag-default than a measured rule. |
| GOV-002 snapshot age | **solid** | Real, simple, parses ISO timestamp from `snapshot_taken_at`. |
| GOV-003 no SDR documentation | **defensible** | Same shape as GOV-001 — fires by default, silenced by signal. Conceptually thin but useful as a default reminder. |
| GOV-005 missing tags (>15%) | **solid (calibrated)** | Threshold p75 = 0.15. Calibration explicit. |
| (GOV-004 missing owners — already excluded from defaults post-calibration as degenerate.) | n/a | Correctly demoted. |

## Gaps — Adobe carries this, no rule grades it

These are the highest-leverage additions because they tap configuration
data the adapter already preserves but the rubric ignores. The AA adapter
dumps every unhandled record field into `Component.platform_specific`;
rules with `platforms: [aa]` could read directly from there.

### AA-specific

1. **eVar allocation + expiration combinations.** Adobe documents three
   allocations (Most Recent / Original Value / Linear) and a set of
   expirations (Page View / Visit / Visitor / Custom Days / Custom Visits
   / Specific Date / Event / Never). Documented pitfall from Adobe's own
   guidance: *"Since Linear allocation accurately distributes values only
   within a visit, use Linear allocation with an eVar expiration of
   Visit."* A `Linear + Visitor` combination is an anti-pattern Adobe
   itself flags. This is exactly the kind of rule sdr-grader exists to
   automate, and the data is already on the snapshot.

2. **Counter-typed events used with currency-shaped names.** Counter
   events store no decimal — using a counter for "Revenue" or "Tax" is
   a silent truncation bug. Similar premise to SCH-004 but for AA event
   types specifically. `event.type` is `counter` / `numeric` / `currency`
   / `numeric_no_subrelations` per Adobe's event-type docs. Currently the
   integer-type whitelist in SCH-004 doesn't even recognize `counter`.

3. **Event serialization gaps on revenue/conversion events.** Adobe
   recommends enabling Event Serialization (Use Event ID) on success
   events that fire on retry-able flows (purchases, signups) to prevent
   duplicate counting. The serialization setting IS in the AA SDR
   snapshot. A rule "revenue/conversion-named event without serialization
   configured" would fire on a real, common bug.

4. **Merchandising eVars without product binding.** Merchandising eVars
   carry product context; non-merchandising eVars don't. Misconfigured
   merch eVars (binding type "Product Syntax" without product data in the
   `s.products` string) produce silent allocation failures. Visible in
   the SDR; not graded.

### CJA-specific

5. **Persistence (lookback) on dimensions.** CJA Data Views set
   persistence per dimension: scope (session / person / custom time
   period) + lookback duration. Per Adobe's docs, persistence is capped
   at 90 days max — and accidentally setting `lookback: 90 days` on a
   dimension that should be session-scoped silently changes attribution
   behavior. The persistence config is in the snapshot. No rule grades it.

6. **Attribution component settings on metrics.** CJA Data Views allow
   per-metric default attribution configuration. A metric whose Data View
   sets a non-default attribution without that being documented in the
   metric description is an analytical landmine. Similar premise to
   ATTR-001 but at the Data View level rather than calc metric level,
   and it ACTUALLY catches the silent-default risk ATTR-001 was reaching
   for.

7. **Derived field cycles and component refs.** Derived fields can chain
   (one derived field references another). The adapter handles dedup
   between inline metrics/dimensions and derived fields, but no rule
   checks for derived-field circular references or for derived fields
   that reference non-existent base components.

### Both platforms

8. **Owner / approval / shared-to-count signals on calc metrics and
   segments.** Adobe's calculated-metrics and segments APIs DO carry
   owner, approval status, and shared-to-count fields (and `aa_auto_sdr`
   pulls them). These are richer than component-level owner attribution
   (which is degenerate per GOV-004). A "high-complexity calc metric
   shared widely but never approved" rule has all the data it needs.

## Recommendations ranked by leverage

1. **Run the ATTR calibration** now that the measurement functions exist
   (`scripts/calibrate_thresholds.py`). Use the result to either ship
   ATTR-002 with a real threshold or demote it to opt-in. 1-hour task.

2. **Add the four highest-value AA gaps** (eVar allocation+expiration,
   counter-type events on currency names, event serialization on
   revenue events, derived-field broken refs). Each is structural,
   doesn't need calibration, and grades data already on the snapshot.
   Estimate ~1 day end-to-end (rule + check + tests + fixture updates).

3. **Refine the regexes in SCH-004 and SCH-005** to reduce false
   positives. Drop `old`, `tmp`, `temp`, `v0` from SCH-005's default
   pattern; add `counter` to SCH-004's integer-type set. ~1 hour.

4. **Decide what to do about the `tag_filter: custom` constraint** in
   NAME-001 and NAME-003. Either drop the constraint and accept some
   platform-default-prefix noise, or document the rules as
   tagging-discipline-dependent. ~30 minutes plus calibration.

5. **Consider expanding NAME-004's default synonym groups** with
   Adobe-domain pairs (`revenue/sales`, `cart/basket`,
   `order/transaction`, `purchase/checkout`). ~15 minutes.

6. **CJA-specific rules** (persistence, attribution at Data View level)
   are higher engineering cost — the CJA adapter needs to extract these
   fields from the snapshot's Data View block — but each replaces or
   subsumes a weaker existing rule. Worth doing after #1–5.

## Sources

- [Conversion Variables (eVar)](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/conversion-var-admin)
- [Success events overview](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/success-event)
- [Change the event type](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/success-events/event-type)
- [Event ID serialization](https://experienceleague.adobe.com/en/docs/analytics/implementation/vars/page-vars/events/event-serialization)
- [Persistence Component Settings (CJA)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/persistence)
- [Attribution component settings (CJA)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/attribution)
- [Metric type and Attribution (calculated metrics)](https://experienceleague.adobe.com/en/docs/analytics/components/calculated-metrics/calcmetric-workflow/m-metric-type-alloc)
- [Attribution Model Application in CJA](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-workspace/attribution/overview)

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

**Verified against:** the 108-fixture private corpus
(`tests/fixtures/private/{aa,cja}/`) loaded through the live adapters,
plus `docs/threshold_calibration.md` and current Adobe Experience League
documentation. Empirical counts cited below come from that vetting pass.

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
| SCH-004 type-name mismatch | **solid as a shape-mismatch detector; counter branch is structurally inert** | Premise (rate/percent name + integer type → silently broken) is real. **Corrected end-to-end trace (2026-05, verified against Adobe's 2.0 swagger and the pitchmuc/aanalytics2 wrapper):** the earlier audit draft claimed `aa_auto_sdr` normalizes `counter → int` upstream — that's wrong, but the broader picture is that **Adobe itself collapses `counter` and `numeric` success events to `INT` server-side** in the 2.0 `/metrics` response. The official 2.0 swagger enum for `AnalyticsMetric.type` is `{STRING, INT, DECIMAL, CURRENCY, PERCENT, TIME, ENUM, ORDERED_ENUM}` — `counter` is not a value the 2.0 API can return. `aa_auto_sdr/api/fetch.py:395` and `sdr_grader/adapters/aa.py:100,116` both pass `type` through verbatim, but the verbatim value is `INT`. The synthetic `aa_auto_sdr/sample_outputs/demo_prod.json` showing `"type": "counter"` is hand-crafted fixture content, not a real API response. **Implications for SCH-004:** (a) the rate/percent + INT/DECIMAL shape check is the load-bearing logic and is correctly wired; (b) the `counter` entry in `_INTEGER_TYPES` (added 1c2abf3) is dead code in the 2.0-API world — it would only fire if a supplementary admin-source (legacy 1.4 `ReportSuite.GetSuccessEvents` or an admin-console export) carrying raw counter types were merged into the snapshot. Keep the entry as forward-compatible scaffolding, but don't expect it to fire against any 2.0-API-sourced snapshot. The 4 hits in the current corpus all fire on the shape-mismatch path, not the counter path. |
| SCH-005 deprecated components still in use | **refined — possibly over-corrected** | Premise is real. The original default regex `\b(deprecated\|legacy\|old\|deleteme\|do_not_use\|v0\|tmp\|temp)\b` was narrowed in 1c2abf3 to drop `old`, `tmp`, `temp`, `v0`. The named false-positive risks (`Holdovers`, `Order Total`, `temperature`, `eVar0`) can't actually trigger the original regex because of word-boundary semantics: `\bold\b` requires a word boundary on both sides, `\bv0\b` won't match inside `eVar0`. On the 108-fixture corpus the old regex fired 149 times and the new regex fires 146 — the 3 dropped components (`"Account Name (old)"`, `"Old Order Status"`, `"Old Page Type"`) all look like genuine deprecation markers. Either re-add `\bold\b` (the abstract false-positive risk didn't materialize) or document the trade-off explicitly. |

## Naming consistency (4 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| NAME-001 prefix consistency | **solid (calibrated, post-fix)** | Original 0/108 dead-by-default state has been resolved: `tag_filter: custom` was removed from both packs in 074b131, so the rule now grades all dimensions. Calibration (2026-05-22, n=108, high confidence) reveals a clean bimodal distribution: p25=0.04, p50=0.07, p75=0.16, **p90=0.82**, p95=1.00 — tenants either operate under no prefix convention (lower 75%) or apply one broadly (top ~10%). The strict-pack threshold 0.60 sits squarely in the inflection between those populations; pragmatic 0.50 still discriminates. Rule will fire on most tenants without a broad convention — appropriate for a `severity: low` "no shared convention" signal. |
| NAME-002 ID pattern | **solid** | AA IDs are constrained system-assigned strings (`evar1`, `event23`); CJA dimension IDs are SchemaPath strings (`variables/evar5`, `metrics/m_orders`). The default pattern `^[A-Za-z0-9_/.\-]+$` accepts both correctly. Real-world bugs from spaces in IDs DO occur (cja_auto_sdr has handled at least one such report). Structural, no calibration needed. |
| NAME-003 casing consistency | **solid (calibrated, post-fix)** | Same fix as NAME-001 (074b131 removed `tag_filter: custom`). Casing classifier itself was always solid (camelCase / PascalCase / snake_case / kebab-case / SCREAMING_SNAKE / Title Case / lowercase phrase). Calibration (2026-05-22, n=108, high confidence): p25=0.64, p50=0.70, p75=0.83, p90=0.90. Smoother than NAME-001 — no bimodal cliff. Strict-pack threshold 0.60 fires on the bottom ~20% of tenants (those mixing styles), pragmatic 0.50 on the bottom ~10%. Reasonable signal-to-noise. |
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
| CALC-003 formula complexity | **solid (calibrated)** | Threshold 22, rounded from p90 = 21.5. Complexity score is computed by `cja_auto_sdr` from the parsed formula AST; matches the upstream tool's own complexity metric. |
| CALC-014 near-duplicates (Jaccard ≥ 0.85) | **solid** | Reference-set Jaccard over calc metric references is a principled near-dup signal. Severity high reflects that this catches the "Revenue (v1)" vs "Revenue (final)" vs "Revenue (canonical)" anti-pattern. |
| CALC-015 identical formula text | **solid** | Different from CALC-014 — same formula bytes, different IDs/names. A copy-paste-and-forget smell. |

## Attribution (3 rules)

The full analysis lives in the conversation transcript that produced this
audit; summary here.

| Rule | Disposition | Notes |
|------|-------------|-------|
| ATTR-001 silent last-touch default | **demoted to opt-in (calibrated)** | Adobe's docs confirm Last Touch IS the platform default when no model is specified, so the premise is real. **Corpus check:** 49 of 49 revenue/order/conversion-named calc metrics (100%) lack a baked-in attribution model — the rule fires on every one of them. At the tenant level the calibration script measures n=3 tenants with any revenue-named calc metrics, all at ratio 1.00. Most are simple ratios where attribution is correctly set at the panel level in Workspace. The rule fires on the common case, not the actually-risky subset (executive-dashboard calc metrics where attribution should be baked in). **Action taken (2026-05):** removed from default `strict` / `pragmatic` packs in 35a57c8; check function stays registered so custom packs can opt in. To re-promote, the rule needs an additional signal (e.g. metric is referenced from a Workspace project export passed via `--extra-input`). |
| ATTR-002 calc metrics lacking explicit attribution > 30% | **demoted to opt-in (degenerate)** | Calibration via `scripts/calibrate_thresholds.py` (run 2026-05-22) confirms p25 = p50 = p75 = p90 = p95 = **1.00** across n=31 tenants with any calc metrics; the script flags the distribution as **degenerate** — every observation sits at 1.00, so no threshold (0.30, 0.99, anywhere in between) distinguishes signal from baseline. Until tenants routinely populate `attribution_model` on calc metrics, the rule cannot discriminate. **Action taken (2026-05):** removed from default packs in 35a57c8; check function stays registered. ATTR-* row added to `threshold_calibration.md` by the same run. |
| ATTR-003 same-refs different-attribution inconsistency | **solid in principle, rare in practice (confirmed)** | When fired, signal is genuine. Conflict requires ≥2 calc metrics with same input refs AND ≥2 distinct non-None attribution models — rare prerequisite. Calibration (2026-05-22) confirms: **0 observations** across 108 corpus entries (no tenant carries the prerequisite data). Keep as-is — the rule earns its keep on the day a tenant DOES populate attribution models on overlapping calc metrics. Structural, no threshold to calibrate. |

## Governance (4 rules)

| Rule | Disposition | Notes |
|------|-------------|-------|
| GOV-001 no snapshot history | **defensible** | Extrinsic signal — the snapshot itself can't carry "is there a directory of older snapshots". Rule fires by default and is silenced by `history_present=true` from the loader / CI when evidence exists. Functions more like a nag-default than a measured rule. |
| GOV-002 snapshot age | **solid** | Real, simple, parses ISO timestamp from `snapshot_taken_at`. |
| GOV-003 no SDR documentation | **defensible** | Same shape as GOV-001 — fires by default, silenced by signal. Conceptually thin but useful as a default reminder. |
| GOV-005 missing tags (>15%) | **solid (calibrated)** | Threshold 0.15, rounded from p75 = 0.14 (p90 = 0.26). Calibration explicit. |
| (GOV-004 missing owners — already excluded from defaults post-calibration as degenerate.) | n/a | Correctly demoted. |

## Gaps — Adobe carries this, no rule grades it

These are the highest-leverage additions because they tap configuration
data the adapter already preserves but the rubric ignores. The AA adapter
dumps every unhandled record field into `Component.platform_specific`;
rules with `platforms: [aa]` could read directly from there.

### AA-specific

> **Blocker (verified 2026-05).** All four AA-specific gaps below share
> the same root cause: the data lives in Adobe's legacy 1.4 Admin API
> (`ReportSuite.GetSuccessEvents`, `GetConversionVars`), not the 2.0
> Reporting API surface that `aa_auto_sdr` consumes via pitchmuc /
> `aanalytics2`. The 2.0 swagger constrains dimension and metric
> records to a small documented field set — neither merchandising
> config, allocation, expiration, nor event serialization is exposed.
> Real-prod sample output from `aa_auto_sdr` (`sample_outputs/`)
> confirms this: every component ships with `extra: {}`. The 8 AA
> fixtures in the private corpus mirror that shape.
>
> Adobe has publicly indicated this admin surface is eventually
> migrating to the 2.0 APIs. Until then, these rules are documented
> here as ready-when-the-data-is — implementing them needs one of:
> (a) `aa_auto_sdr` wrapping the 1.4 Admin API and surfacing fields
> through `Component.extra`, (b) `sdr_grader` accepting a
> `--extra-input` admin-console export, or (c) waiting for Adobe's
> 2.0 admin endpoints to ship. The audit keeps these gaps in scope
> so the data shape and check logic stay designed; the rule files
> just don't exist yet.

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
   a silent truncation bug. Per Adobe's current success-event docs,
   `event.type` is `counter` / `numeric` / `currency`. (An earlier
   draft of this audit also listed `numeric_no_subrelations`; no
   current Experience League page documents that as a present type, so
   it's been dropped.) **Wiring constraint (corrected 2026-05):** this
   rule is **not implementable from the 2.0 `/metrics` endpoint
   alone**. Adobe's 2.0 API swagger constrains `AnalyticsMetric.type`
   to `{STRING, INT, DECIMAL, CURRENCY, PERCENT, TIME, ENUM,
   ORDERED_ENUM}` — counter and numeric success events both surface as
   `INT`, indistinguishable from each other. The raw counter / numeric
   / currency polarity lives only in (a) the legacy 1.4 Admin REST API
   `ReportSuite.GetSuccessEvents` (not wrapped by `aa_auto_sdr` or
   pitchmuc's `aanalytics2`), or (b) an Admin Console UI export.
   Implementing this rule requires either integrating that 1.4 endpoint
   in `aa_auto_sdr` (upstream change), accepting a `--extra-input`
   admin-console export in `sdr_grader`, or inverting the check: flag
   metrics whose reported 2.0 type is `INT` / `DECIMAL` but whose name
   implies `CURRENCY` (a shape-mismatch detector that uses only data
   already on the snapshot — this is essentially what SCH-004 already
   does for the rate/percent variant and could be extended).

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

> **Corpus check.** Unlike the AA half, CJA snapshots in the private
> corpus carry rich configuration data: across 100 CJA fixtures,
> **19,680 dimensions** populate `persistenceSetting` (with full
> allocation-model, expiration-context, lookback, and merchandising
> sub-configs) and **8,825 metrics** populate `attributionSetting`
> (with model + lookback-period). The data is there today.

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

7. **Derived field cycles and component refs.** ~~No rule checks for
   derived-field circular references or for derived fields that
   reference non-existent base components.~~ **Shipped (2026-05) as
   SCH-008 and SCH-009.** The corpus carries 970 derived fields across
   100 CJA fixtures with full reference/lookup/schema graphs, so the
   data shape was easy to design against. Key findings during
   implementation:
   (a) CJA snapshots store dimensions under `variables/` but derived
   fields reference them via `dimensions/` interchangeably — the rule
   normalizes bare IDs across that namespace boundary before declaring
   a ref missing;
   (b) `lookup_references` and `schema_fields` carry XDM schema paths
   like `<schema-id>.<field>`, not component IDs — these go through
   a different resolver and are intentionally excluded from the
   component-graph check;
   (c) CJA platform built-ins (`metrics/adobe_*`, `dimensions/daterange*`,
   `dimensions/timepart*`, `dimensions/platform*` etc.) are referenced
   constantly but not enumerated in the SDR — the rule filters them
   via regex.
   The 100-fixture corpus contains 0 DF-to-DF chains and 0 genuine
   broken refs after normalization + built-in filtering — but the bug
   class is real in production Data Views, and both rules are
   structurally correct, conservative, and will fire when those
   patterns DO occur. Same shipping rationale as ATTR-003.

### Both platforms

8. **Owner / approval / shared-to-count signals on calc metrics and
   segments.** Adobe's calculated-metrics and segments APIs DO carry
   owner, approval status, and shared-to-count fields (and `aa_auto_sdr`
   pulls them). These are richer than component-level owner attribution
   (which is degenerate per GOV-004). A "high-complexity calc metric
   shared widely but never approved" rule has all the data it needs.

## Recommendations ranked by leverage

1. ~~**Run the ATTR calibration**~~ **Done (2026-05-22).** Calibration via
   `scripts/calibrate_thresholds.py` confirms ATTR-002 is degenerate
   (p25–p95 all at 1.00, n=31), ATTR-001 fires on every revenue-named
   calc metric in the corpus (3 of 3 tenants at ratio 1.00), and ATTR-003
   has 0 observations (no tenant has the prerequisite). ATTR-001 and
   ATTR-002 were demoted to opt-in in 35a57c8; ATTR-003 stays in defaults
   as a structural rule. See ATTR-* rows in
   `threshold_calibration.md` for the underlying distributions.

2. **Add the four highest-value AA gaps** (eVar allocation+expiration,
   counter-type events on currency names, event serialization on
   revenue events, derived-field broken refs). Each is structural,
   doesn't need calibration, and grades data already on the snapshot.
   Estimate ~1 day end-to-end (rule + check + tests + fixture updates).

3. **Refine the regexes in SCH-004 and SCH-005** to reduce false
   positives. Drop `old`, `tmp`, `temp`, `v0` from SCH-005's default
   pattern (1c2abf3); `\bold\b` later restored (d7001c8) after a corpus
   pass confirmed the named false positives don't materialize.
   `counter` was added to SCH-004's `_INTEGER_TYPES` in 1c2abf3 — kept
   as forward-compat scaffolding, but now known to be structurally
   inert against 2.0-API-sourced snapshots (Adobe collapses counter →
   INT server-side). The load-bearing logic in SCH-004 is the
   rate/percent + INT/DECIMAL shape check, which fires correctly.

4. ~~**Decide what to do about the `tag_filter: custom` constraint**~~
   **Done (2026-05).** Constraint removed from default packs in 074b131;
   `tag_filter` remains a check-function parameter for custom packs.
   NAME-001 and NAME-003 measurements added to
   `scripts/calibrate_thresholds.py` and the 2026-05-22 run confirms both
   thresholds (0.60 strict, 0.50 pragmatic) land at defensible inflection
   points (NAME-001 is bimodal with a clean cliff between p75 and p90;
   NAME-003 is smoother but the threshold still discriminates the bottom
   ~20% from the rest). High calibration confidence on both.

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
- [Attribution Models (CJA Workspace)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-workspace/attribution/models)
- [Manage calculated metrics](https://experienceleague.adobe.com/en/docs/analytics/components/calculated-metrics/calcmetric-workflow/cm-manager)
- [Manage segments (CJA)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-components/segments/seg-manage)
- [Derived fields](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/derived-fields)

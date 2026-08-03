# Rubric audit — bundled pack 2.0

This premise audit is synchronized to the YAML shipped in both bundled `2.0`
packs. `strict` and `pragmatic` contain the same 27 rule IDs in the same six
categories; their parameters and severities may differ. The YAML and registered
check functions are the runtime authorities when this narrative drifts.

The May 2026 private-cohort work cited below was compatibility evidence, not an
admitted grading-calibration cohort. The 108 snapshots (100 CJA, 8 AA) helped
exercise adapters and premises, but zero entries met the later calibration
admission contract. Thresholds therefore remain maintainer judgment.

Dispositions mean:

- **Solid** — the normalized model carries the signal and the check tests a
  defensible structural or ratio-based premise.
- **Limited** — the signal is useful but extrinsic, rare, or dependent on
  evidence that a snapshot may not carry.
- **Opt-in** — the registered check exists but is intentionally absent from
  both bundled packs. Opt-in checks are discussed separately and never counted
  as bundled rules.

## Schema hygiene (8 bundled rules)

| Rule | Disposition | Runtime-aligned note |
|---|---|---|
| SCH-001 | Solid | Detects duplicate names within the same normalized `Component.component_type` across metrics, dimensions, and derived fields. |
| SCH-002 | Solid | Resolves segment and calculated-metric references against normalized component, segment, and calculated-metric IDs. |
| SCH-003 | Solid | Measures the maximum missing-description ratio across normalized metrics and dimensions; pack parameters set the threshold. |
| SCH-004 | Solid | Detects rate/percent-shaped names paired with integer-shaped normalized data types. Adobe's AA 2.0 API collapses counter/numeric detail, so this is a shape check, not an admin-event-type audit. |
| SCH-005 | Solid | Uses tags and bounded name markers to find deprecated normalized components that still have consumers. |
| SCH-007 | Solid, CJA-only | Reads the documented `persistenceSetting` extension in `Component.platform_specific` and enforces the 90-day CJA lookback cap. Persistence is graded; it is not a missing pack-2.0 capability. |
| SCH-008 | Solid, CJA-only | Detects cycles among normalized derived-field component references. |
| SCH-009 | Solid, CJA-only | Resolves derived-field component references after CJA namespace normalization and built-in filtering. |

## Naming consistency (4 bundled rules)

| Rule | Disposition | Runtime-aligned note |
|---|---|---|
| NAME-001 | Solid | Measures the dominant prefix ratio across normalized dimensions; bundled packs do not restrict it to a `custom` tag. |
| NAME-002 | Solid | Validates IDs across metrics, dimensions, derived fields, calculated metrics, and segments using the pack regex. |
| NAME-003 | Solid | Measures dominant casing across normalized dimension names; bundled packs do not restrict it to a `custom` tag. |
| NAME-004 | Solid | Detects mixed synonym vocabularies, including the shipped Adobe-domain groups for revenue/sales, cart/basket, order/transaction, and purchase/checkout. |

## Segment complexity (5 bundled rules)

| Rule | Disposition | Runtime-aligned note |
|---|---|---|
| SEG-002 | Solid | Uses normalized `Segment.container_types` to detect mixed CJA or AA container scopes. |
| SEG-004 | Solid | Detects cycles in normalized `Segment.references`. |
| SEG-005 | Solid | Measures the missing-description ratio across normalized segments. |
| SEG-006 | Solid | Canonicalizes normalized `Segment.definition` values to detect duplicate definitions. |
| SEG-007 | Solid | Enforces the pack's maximum normalized `Segment.nesting_depth`. |

## Calculated metrics (5 bundled rules)

| Rule | Disposition | Runtime-aligned note |
|---|---|---|
| CALC-001 | Solid | Measures the missing-description ratio across normalized `CalculatedMetric` records. |
| CALC-002 | Solid | Resolves normalized calculated-metric formula references. |
| CALC-003 | Solid | Enforces the pack threshold against normalized `CalculatedMetric.complexity_score`. |
| CALC-014 | Solid | Uses Jaccard similarity over normalized `CalculatedMetric.references` to find near-duplicates. |
| CALC-015 | Solid | Finds distinct calculated metrics with identical normalized `formula_text`. |

## Attribution (2 bundled rules)

| Rule | Disposition | Runtime-aligned note |
|---|---|---|
| ATTR-003 | Solid but rare | Flags inconsistent non-empty `CalculatedMetric.attribution_model` values among metrics with the same normalized references. The premise is structural even when explicit models are uncommon. |
| ATTR-004 | Solid, CJA-only | Reads the documented `attributionSetting` extension in metric `Component.platform_specific` and requires a description to explain a non-default Data View override. Data View attribution is graded; it is not a missing pack-2.0 capability. |

`ATTR-001` (silent last-touch default) and `ATTR-002` (ratio lacking explicit
attribution) remain registered for custom packs but are not bundled. Historical
compatibility observations were degenerate: the former fired on every
revenue-named calculated metric in its small eligible subset, and the latter
sat at 1.00 across its measured percentiles. Keeping them opt-in avoids counting
the common baseline as a default quality defect.

## Governance (3 bundled rules)

| Rule | Disposition | Runtime-aligned note |
|---|---|---|
| GOV-001 | Limited, explicit evidence | Uses normalized `Implementation.history_present`; directory/trend input can establish history while a lone snapshot often cannot. |
| GOV-003 | Limited, explicit evidence | Uses documented SDR metadata or documented supplementary input to decide whether implementation documentation exists. |
| GOV-005 | Solid | Measures missing tags across normalized metric, dimension, and derived-field `Component.tags`. |

`GOV-002` (snapshot age), `GOV-004` (missing owners), and the pack-1.0 absolute
sharing-count rules are not bundled. The model still has real owner, approval,
and sharing vocabulary: `Component.owner`, plus `Segment` and
`CalculatedMetric` fields `owner`, `approved`, and `shared_to_count`. Their
absence from pack 2.0 is deliberate: no current default rule turns raw tenant
size or sharing volume into a quality penalty.

## Remaining coverage gaps

The shipped CJA persistence and Data View attribution rules close the two gaps
claimed by older revisions of this audit. The remaining high-value gaps are
AA admin settings that the current AA 2.0 Reporting API snapshot does not
provide:

1. eVar allocation and expiration combinations.
2. Raw success-event type distinctions such as counter versus numeric.
3. Event serialization on retry-prone conversion events.
4. Merchandising eVar product-binding configuration.

Do not implement these by probing arbitrary `Implementation.raw` paths. Add a
documented `--extra-input KEY=PATH` contract, or wait for the upstream snapshot
exporter to supply the setting and normalize it into an explicit model field or
documented `platform_specific` key. Until that evidence exists, AA correctly
runs the 23 applicable bundled rules and excludes SCH-007, SCH-008, SCH-009,
and ATTR-004 from its scoring denominator.

## Sources

- [Conversion Variables (eVar)](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/conversion-var-admin)
- [Success events overview](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/success-event)
- [Change the event type](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/success-events/event-type)
- [Event ID serialization](https://experienceleague.adobe.com/en/docs/analytics/implementation/vars/page-vars/events/event-serialization)
- [Persistence Component Settings (CJA)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/persistence)
- [Attribution component settings (CJA)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/component-settings/attribution)
- [Metric type and Attribution (calculated metrics)](https://experienceleague.adobe.com/en/docs/analytics/components/calculated-metrics/calcmetric-workflow/m-metric-type-alloc)
- [Manage calculated metrics](https://experienceleague.adobe.com/en/docs/analytics/components/calculated-metrics/calcmetric-workflow/cm-manager)
- [Manage segments (CJA)](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-components/segments/seg-manage)
- [Derived fields](https://experienceleague.adobe.com/en/docs/analytics-platform/using/cja-dataviews/derived-fields)

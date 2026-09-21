# AA administration evidence

The default `strict@3.0` and `pragmatic@3.0` packs include four AA-only rules
comparing administration settings with separately declared business expectations.
AA has 27 applicable checks in their 31-rule catalog. CJA also has 27 applicable
checks; the four CJA-only rules remain CJA-only. The grader remains an offline
linter and never authenticates to Adobe.

```bash
sdr-grader snapshot.json --extra-input aa_admin=aa-admin.json \
  --output grade.html --json grade.json
```

| Rule | Declared target settings compared |
| --- | --- |
| AA-001 | eVar allocation and expiration, including custom days when expiration is `day` |
| AA-002 | Success-event type: counter, numeric, or currency |
| AA-003 | Event serialization configuration |
| AA-004 | Merchandising syntax and allocation; binding event IDs for conversion-variable syntax |

The default packs place AA-001 and AA-004 in attribution coverage and AA-002
and AA-003 in schema hygiene, retaining the six existing category weights.
The standalone `--pack aa-admin` pack remains available at version 1.0 for a
separate report containing only these four checks.

Configuration matches do **not** prove runtime event-ID delivery, deduplication,
product binding, or collection correctness. Expectations must come from the
implementation's business requirements. The grader does not infer appropriate
event types or serialization settings from component names.

## Collection and provenance

1. Export an AA snapshot for the intended report suite with `aa_auto_sdr`.
2. Obtain eVar settings using Adobe's Analytics 2.0 Dimensions API with the
   relevant expansions: `allocationType`, `expirationType`,
   `expirationCustomDays`, `merchandisingSyntax`, and `bindingEvents`. Preserve
   these fields on each dimension record or under its `extra` object. Current
   exporter configurations may request only descriptions and tags, so inspect
   the actual export; a field absent from the export is not evidence of its value.
3. If your export lacks those fields, transcribe sourced eVar settings into
   `observations.evars`. Obtain success-event type and serialization from an
   authorized, reviewed Admin configuration export or operator transcription
   and place them in `observations.events`. Analytics 2.0's reporting metric
   `type` or `dataType` is **not** the success-event type and is never used as that evidence.
4. Record the report suite, collection time, and source description. Declare
   the intended settings separately in `expectations`, then run the command.

Adobe documents the eVar fields and their tokens in the
[Dimensions API reference](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/dimensions/).
Its [Analytics API migration guide](https://developer.adobe.com/analytics-apis/docs/2.0/guides/migration)
identifies eVar configuration as readable and success-event configuration as
unavailable through Analytics 2.0. This workflow does not add a legacy API 1.4
collector. Review credentials and collect evidence in your existing authorized
tooling; no credentials belong in either JSON input.

## Version 1 protocol

The root object requires exactly these fields: integer `schema_version: 1`,
`platform: "aa"`, `report_suite_id` matching the snapshot, a parseable
`captured_at` timestamp, nonempty `source` provenance text, `observations`, and
`expectations`. Prefer an ISO-8601 timestamp with an explicit timezone.
Timestamps are evidence metadata; the grader does not infer freshness.

Both sections are objects with optional `evars` and `events` arrays. Missing
arrays mean no supplied records. Each record requires a unique, case-sensitive
`id`: `variables/evarN` or `metrics/eventN`, where N is a positive integer.
Unknown keys, duplicate records or binding IDs, malformed values, invalid
expectation tokens, and mismatched suites are controlled input errors. Error
messages do not echo input values. This validation runs only when AA admin
checks are selected for AA.

EVar fields use these normalized names:

| Field | Allowed values |
| --- | --- |
| `allocation` | `most_recent_last`, `original_value_first`, `linear`, `linear_to_items`, `merchandising_first`, `merchandising_last` |
| `expiration` | `visit`, `page_view`, `never`, `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`, `purchase`, `product_view`, `cart_open`, `cart_checkout`, `cart_add`, `cart_remove`, `cart_view`, `event` |
| `expiration_days` | Positive integer; required when `expiration` is `day` |
| `merchandising_syntax` | `product`, `conversion_variable` |
| `binding_events` | Array of full `metrics/…` IDs with a nonempty suffix and no whitespace, compared as a set; required for `conversion_variable` |

The adapter maps `allocationType` → `allocation`, `expirationType` →
`expiration`, `expirationCustomDays` → `expiration_days`,
`merchandisingSyntax` → `merchandising_syntax`, and `bindingEvents` →
`binding_events`. Top-level dimension fields, dimension `extra` fields, and
supplementary observations must agree wherever they overlap. There is no
last-source-wins precedence. Product syntax requires no binding event list;
AA-004 ignores binding lists for product syntax.

Event fields are `event_type` (`counter`, `numeric`, `currency`) and
`serialization` (`always`, `once_per_visit`, `use_event_id`). Serialization
values are **operator-normalized protocol tokens**, not a claim about Analytics
2.0 response fields: map the Admin choices Always record event, Record once per
visit, and Use event ID to those three values respectively.
See Adobe's [Success Events administration guide](https://experienceleague.adobe.com/en/docs/analytics/admin/admin-tools/manage-report-suites/edit-report-suite/conversion-variables/success-event)
for event types and Unique Event Recording. The
[serialization implementation guide](https://experienceleague.adobe.com/en/docs/analytics/implementation/vars/page-vars/events/event-serialization)
explains why enabling Use Event ID alone does not establish deduplication:
hits without an ID still count.

Unknown nonempty observation strings are retained as unsupported evidence.
They make the affected check unassessed. They never become default settings.
Missing fields, null values, and empty binding arrays are different. API nulls
on dimension records (including `extra`) mean unavailable or not-applicable
evidence and are omitted during normalization; they never supply required
settings or defaults. Nulls in the supplementary version 1 protocol are
malformed. Missing fields mean unavailable evidence. An empty binding array is
an explicit observed or expected empty set.

## Complete example

This standalone supplementary file supplies observations for all four rules.
The snapshot must belong to report suite `suite`; supplied API fields must agree.

```json
{
  "schema_version": 1,
  "platform": "aa",
  "report_suite_id": "suite",
  "captured_at": "2026-09-20T00:00:00Z",
  "source": "Synthetic example; replace with reviewed export/transcription provenance",
  "observations": {
    "evars": [{
      "id": "variables/evar1",
      "allocation": "most_recent_last",
      "expiration": "day",
      "expiration_days": 30,
      "merchandising_syntax": "conversion_variable",
      "binding_events": ["metrics/event1"]
    }],
    "events": [{
      "id": "metrics/event1",
      "event_type": "counter",
      "serialization": "use_event_id"
    }]
  },
  "expectations": {
    "evars": [{
      "id": "variables/evar1",
      "allocation": "most_recent_last",
      "expiration": "day",
      "expiration_days": 30,
      "merchandising_syntax": "conversion_variable",
      "binding_events": ["metrics/event1"]
    }],
    "events": [{
      "id": "metrics/event1",
      "event_type": "counter",
      "serialization": "use_event_id"
    }]
  }
}
```

## Assessment and scoring

A rule's scope is only the explicitly declared expectations for its settings.
AA-001 selects eVar records declaring allocation or expiration (including days);
AA-004 selects records declaring merchandising syntax or binding events and
also requires allocation. AA-002 and AA-003 select event records declaring
their respective field. Fields needed by a selected rule must be complete in
both observations and expectations for **every** declared target.

If the supplementary input is absent, the rule has no declared targets, or any
target lacks required or supported observations/expectations, the **entire
rule** is excluded from execution and the scoring denominator. This is
reported under methodology skipped rules in HTML and JSON. A partial inventory
cannot earn a pass by silently dropping difficult targets. Even passing rules
list the limited declared target scope in methodology. A category with no
assessed rules has an arithmetic score of 100 with an explicit disclosure that
this is not verification.

In the standalone pack, if AA-003 is unassessed and only AA-002 fails, three equally weighted
rules are assessed and the score is 67, not 75. This explicit gating is specific
to AA admin checks; older supplementary checks may stay silent while still
remaining in their rubric's denominator.

Default pack 3.0 is a scoring-policy change from 2.1 and requires grader 1.5.0
or the current 1.5.0 candidate. Complete AA evidence adds
the rules to their category severity denominators; a mismatch can lower a score,
and a passing rule can change the relative share of existing failures. Without
AA admin evidence the four rules are excluded, preserving prior numeric scores
while adding explicit skipped-rule disclosures. CJA scores are unchanged.
Regrade comparison snapshots under one pack version; do not compare a standalone
four-rule score with the full default-pack score. The released grader 1.4.0
cannot load pack 3.0 because it lacks these checks. Until 1.5.0 is published,
use only the current 1.5.0 candidate build for pack 3.0 evaluation. Do not copy
pack 3.0 into a released 1.4.0 installation. Historical pack 2.1 policy
references for grader 1.4.0 remain valid.

## Verification boundary

`tests/fixtures/aa_admin/` and `tests/test_aa_admin.py` validate synthetic API
shapes, supplementary observations, scoring exclusions, individual pass/fail
cases, determinism, and CLI HTML/JSON output. They do not constitute a live
Adobe tenant verification. No live credentials, live exports, or live
administration changes were exercised for this implementation.

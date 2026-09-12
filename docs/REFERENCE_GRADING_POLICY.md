# Reference grading policy 2.1

Grader 1.4.0 with bundled strict or pragmatic 2.1 excludes explicitly typed,
unresolved calculated-metric-to-segment references from SCH-002 and CALC-002.
This applies equally to AA and CJA. The references remain unresolved and
unverified. Snapshot absence cannot distinguish internal/project-only omissions
from deleted, inaccessible, or otherwise unavailable segments. Genuinely invalid
references in this category therefore also become unscored. Exclusion establishes
neither availability nor validity, project ownership, lifecycle, or scope.

Existing snapshots work without re-export. No exporter production changes,
`reference_evidence` field, snapshot schema changes, credentials, or Adobe API
collection are required. Exporter enrichment is a separately deferred capability,
with its own future source contract; its earlier evidence gates do not apply here.

## Eligibility

Existing inventory and alias resolution runs first, using the existing known-ID
union. A resolved reference keeps its previous result and receives no exclusion
diagnostic. This policy does not introduce type-aware resolution, suffix matching,
new aliases, or inventory entries. Canonical reference lists, order, formulas,
inventories, aliases, and relationships remain unchanged for other checks.

Adapters retain definition-derived kinds and uncertainty beside each calculated
metric. Only an unresolved canonical ID with exactly segment typing and no
blocker qualifies. Duplicate calculated-metric consumer IDs prevent exemption;
existing duplicate-segment validation remains unchanged.

| Source or condition | Result |
|---|---|
| AA `func: segment-ref` with a nonempty string `id` | Segment typing from the full definition, including outer filters |
| CJA `func: segment-ref` or `segment`, scalar `segment_id` or existing `id` fallback | Segment typing; conflicting identity slots block exemption |
| CJA `segment` object/list identity wrapper | Supported only when usable identity candidates agree; preserve existing first-selected canonical reference even if ambiguous |
| `metric/name`, `event/name`, `attr/name` | Metric, metric, dimension: remain scoring candidates |
| Exact ID typed as segment in definition but metric in a legacy summary | Definition wins; the summary cannot grant or block eligibility |
| Existing unique same-kind summary abbreviation reconciliation | Keep the already-established canonical association |
| Summary-only or independent ambiguous summary abbreviation | Unknown, retain existing scoring |
| AA bare namespaced strings in `args`, including `segments/…` | Untyped; ID shape never establishes eligibility |
| Missing, empty, invalid optional definition; legacy normalized model without metadata | Unknown; preserve existing fallback and scoring |
| Same ID typed segment plus another kind or untyped operand | Conflicting/unknown; no exemption |
| Malformed identity, unsupported identity occurrence, multi-target wrapper | Block affected canonical IDs; independent well-typed siblings may qualify |
| Literal or metadata content | Cannot provide reference typing |

Structured traversal is limited to object/list children in `formula`, `args`,
`col`, `col1`, `col2`, `metric`, `filter`, `filters`, `container`, `pred`, `preds`,
`val`, and `evt`. It does not traverse `str`, `list`, `glob`, `description`,
`name`, arbitrary extension keys, or AST-like text strings. Unknown operators
cannot type their own IDs, but supported children in allowed positions can.
Existing depth, node, and Unicode limits and input-error outcomes remain intact.

CJA wrapper `segment_id` and `id` are explicit identity slots. `name` alongside
an explicit ID is a label. Only absent explicit slots allow `name`, `metric`,
`value`, or `val` identity fallback. Empty/null sentinels are ignored as before;
multiple distinct usable targets or malformed identity candidates block exemption.
Repeated identical targets do not introduce ambiguity.

## Scoring and diagnostics

Let E be excluded unresolved references, Q all nonexcluded candidates (including
resolved references), and F the unresolved subset of Q, separately for each rule.
SCH-002 includes segment and calculated-metric consumers; CALC-002 includes only
calculated-metric consumers. Segment-consumer references never receive this exemption.

| Population | Assessment and score |
|---|---|
| E empty, including no references | Previous behavior |
| E nonempty, Q empty | Rule not assessed; remove its severity from denominator; no Finding |
| E and Q nonempty, F empty | Keep rule assessed and denominator; no scored failure; E stays unverified |
| E and F nonempty | Keep existing full per-rule penalty and denominator; Finding contains only F |
| Same remaining failure covered by both rules | Both existing penalties remain |

Severity, category weights, rounding, and grade bands are unchanged. An empty
category keeps its arithmetic default of 100; summary and methodology identify
it as unassessed, not verified. If no scoring rules are assessed, the summary
starts “No scoring rules were assessed”; numeric and threshold defaults remain.
Inventory component counts do not treat excluded relationships as skipped components.

Schema-1 `methodology.paragraphs` contains a policy explanation and one diagnostic
per distinct canonical consumer-kind/consumer-ID/target-ID tuple, sorted by that
tuple. Associated rule IDs are sorted and combined:

> Unverified reference: calculated metric cm → segment s. Unresolved in this snapshot; excluded from grading by CALC-002, SCH-002.

Only configured, platform-applicable, policy-enabled rules without full user
suppression participate, including rules then skipped by the policy. A zero
category weight does not suppress a rule. Finding-level suppression does not
erase diagnostics. Neither participating rule means no exclusion diagnostic.

Each excluded-only rule gets its own `methodology.skipped` entry:

> Not assessed: all reference candidates were excluded by the calculated-metric-to-segment policy; the references remain unverified.

Partial exclusions are not whole-rule skips. Diagnostics are escaped, deterministic,
and deliberately uncapped in HTML and JSON; the 50-item HTML finding cap does not
apply. They never contribute Findings, remediations, fired-rule counts, threshold
inputs, or finding churn. These paragraphs are human-readable diagnostics, not a
new structured machine-queryable reference API. Report schema keys and types stay 1.

## Custom packs and historical comparisons

The boolean check parameter `exclude_unresolved_calculated_metric_segments`
controls the policy, not the version string. Both bundled packs enable it in
both checks. Omitted or false preserves previous behavior for custom packs;
nonboolean values fail rubric loading. Custom rule IDs work through the same
registered check names. Policy 2.1 requires grader 1.4.0 or later: older graders
ignore the new parameter and are unsupported with a new policy pack.

Regrade every historical snapshot in a comparison with the same grader and pack.
Stored reports made under different policies may differ in findings, denominators,
scores, grades, and threshold exits. Removing entries from a mixed Finding alone
does not reduce its per-rule penalty. Removing an excluded-only rule's denominator
can increase the relative share of other failures.

The September 12 six-pair CJA counterfactual stayed at 38 strict / 53 pragmatic,
with both affected rules firing and 27 effective rules. It is dated evidence,
not a promise about full-policy results or another snapshot. The public acceptance
fixtures and exact compatibility expectations are under
`tests/fixtures/reference_grading_policy/`; historical correctness baselines remain
under `tests/fixtures/correctness_1_3/` without replacement.

Visualizer uncertainty wording is independent. It retains unresolved and ambiguous
status, catalog navigation, graph connectivity, counts, diff, and trend behavior;
it does not claim a grading policy was applied to a descriptive catalog.

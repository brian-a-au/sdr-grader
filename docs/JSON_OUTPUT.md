# JSON output reference

`sdr-grader --json PATH` writes the machine-readable form of the same `Report`
used by the HTML renderer. This page is the canonical public reference for that
format. The runtime authorities are `REPORT_SCHEMA_VERSION`, `report_to_dict()`,
and the report dataclasses in `src/sdr_grader/render/`.

Schema version: `1`

Schema 1 always emits every key shown below. A required key may still have a
documented `null` value. For a row ending in `[]`, the row describes each array
item; nested required keys apply whenever that parent object or item exists.
Arrays may be empty.

## Stable consumer fields

Use these fields when identifying or comparing evaluations:

| Purpose | Paths |
|---|---|
| Schema identity | `schema_version` |
| Evaluated instance identity | `instance_id`, `instance_name` |
| Source identity | `adapter.platform`, `adapter.tool`, `adapter.version` |
| Rubric identity | `rubric.pack`, `rubric.version` |
| Grader identity | `tool_version`, `tool_url` |
| Grade result | `grade`, `overall_pct`, `categories[]` |
| Audit result | `findings[]`, `remediations[]`, `methodology` |
| Evaluation time | `generated_at` |

`id` is the report's synthetic display identifier. Use `instance_id`, not `id`
or the human-readable `instance_name`, as the stable implementation identity.
`generated_at` is an ISO-8601 UTC string ending in `Z`.

## Complete serialized shape

| Path | JSON type | Required key | Meaning |
|---|---|---|---|
| `schema_version` | `integer` | yes | Format version, currently 1 |
| `id` | `string` | yes | Synthetic report identifier |
| `instance_name` | `string` | yes | Human-readable implementation name |
| `instance_id` | `string` | yes | Stable data view or report suite identity |
| `grade` | `string` | yes | Overall letter grade |
| `overall_pct` | `integer` | yes | Overall score from 0 through 100 |
| `components_evaluated` | `integer` | yes | Count of components evaluated |
| `components_skipped` | `integer` | yes | Count of components skipped |
| `components_skipped_reason` | `string or null` | yes | Explanation when components were skipped |
| `adapter` | `object` | yes | Snapshot adapter identity |
| `adapter.platform` | `string` | yes | Platform code such as CJA or AA |
| `adapter.tool` | `string` | yes | Source adapter or generator family |
| `adapter.version` | `string` | yes | Source adapter or generator version |
| `rubric` | `object` | yes | Rubric pack identity |
| `rubric.pack` | `string` | yes | Pack name |
| `rubric.version` | `string` | yes | Pack version |
| `generated_at` | `string` | yes | Evaluation timestamp in ISO-8601 UTC |
| `tldr_html` | `string` | yes | Generated summary containing reviewed HTML fragments |
| `categories` | `array` | yes | Category score records |
| `categories[]` | `object` | yes | One category score |
| `categories[].name` | `string` | yes | Display name |
| `categories[].pct` | `integer` | yes | Category score from 0 through 100 |
| `categories[].grade` | `string` | yes | Category letter grade |
| `remediations` | `array` | yes | Severity-ordered remediation summaries |
| `remediations[]` | `object` | yes | One remediation summary |
| `remediations[].text` | `string` | yes | Recommended action |
| `remediations[].refs` | `array` | yes | Related rule IDs |
| `remediations[].refs[]` | `string` | yes | One related rule ID |
| `remediations[].priority_weight` | `integer` | yes | Severity-derived ordering weight |
| `remediations[].impact_pts` | `integer` | yes | Deprecated alias of priority weight |
| `findings` | `array` | yes | Fired rule findings |
| `findings[]` | `object` | yes | One finding |
| `findings[].id` | `string` | yes | Stable rule ID |
| `findings[].severity` | `string` | yes | critical, high, medium, or low |
| `findings[].category` | `string` | yes | Category display name |
| `findings[].title` | `string` | yes | Finding title |
| `findings[].body` | `array` | yes | Ordered body blocks |
| `findings[].body[]` | `object` | yes | One body block |
| `findings[].body[].kind` | `string` | yes | Body variant discriminator |
| `findings[].body[].html` | `string or null` | yes | Paragraph content when applicable |
| `findings[].body[].label` | `string or null` | yes | Section label when applicable |
| `findings[].body[].body_html` | `string or null` | yes | Section body when applicable |
| `findings[].body[].items` | `array or null` | yes | Component rows when applicable |
| `findings[].body[].items[]` | `string` | yes | One component row |
| `findings[].body[].text` | `string or null` | yes | Code or preformatted text when applicable |
| `findings[].actions` | `array` | yes | Optional navigation actions |
| `findings[].actions[]` | `object` | yes | One finding action |
| `findings[].actions[].label` | `string` | yes | Link label |
| `findings[].actions[].href` | `string` | yes | Link target; validate before navigation |
| `methodology` | `object` | yes | Method and suppression disclosure |
| `methodology.paragraphs` | `array` | yes | Ordered methodology paragraphs |
| `methodology.paragraphs[]` | `string` | yes | One paragraph containing reviewed HTML fragments |
| `methodology.skipped` | `array` | yes | Suppressed or skipped-rule groups |
| `methodology.skipped[]` | `object` | yes | One skipped-rule group |
| `methodology.skipped[].ids` | `array` | yes | Rule IDs in the group |
| `methodology.skipped[].ids[]` | `string` | yes | One skipped rule ID |
| `methodology.skipped[].reason` | `string` | yes | Recorded skip reason |
| `distribution` | `object or null` | yes | Optional reference-distribution charts |
| `distribution.charts` | `array` | yes | Distribution chart records |
| `distribution.charts[]` | `object` | yes | One distribution chart |
| `distribution.charts[].label` | `string` | yes | Provenance-neutral chart label |
| `distribution.charts[].svg` | `string` | yes | Generated inline SVG |
| `tool_version` | `string` | yes | `sdr-grader` version |
| `tool_url` | `string` | yes | Canonical project URL |

## Finding body variants

Every body block emits `kind`, `html`, `label`, `body_html`, `items`, and
`text`. Fields not used by that block are `null`; a `section` may also have a
null `body_html` when it acts as a label before a following block.

| `kind` | Content field or fields | Interpretation |
|---|---|---|
| `paragraph` | `html` | Paragraph content |
| `section` | `label`, optionally `body_html` | Labeled section or label-only lead-in |
| `components` | `items` | Array of component rows |
| `code` | `text` | Raw text intended for preformatted display |

Consumers should switch on `kind` and ignore inactive fields rather than
guessing the variant from which field happens to be non-null.

## HTML-bearing strings and trust

The Python report model can preserve `Markup` objects for reviewed renderer
sinks. JSON has no equivalent trust marker: after serialization, every value
below is just a string. A consumer must not infer safety from a field name or
from the fact that the bundled HTML renderer trusted an internal value.

| Path | Renderer source | JSON consumer rule |
|---|---|---|
| `tldr_html` | maintainer-generated trusted markup | Treat as an ordinary JSON string; escape for text or sanitize before an HTML sink |
| `methodology.paragraphs[]` | maintainer-generated trusted markup | Treat as an ordinary JSON string; escape for text or sanitize before an HTML sink |
| `findings[].body[].html` / `body_html` | untrusted text | Treat as an ordinary JSON string; never insert directly into an HTML sink |
| `distribution.charts[].svg` | maintainer-generated trusted SVG | Treat as an ordinary JSON string; sanitize before embedding outside the bundled renderer |

All other report strings, including action labels and targets, component rows,
rule-derived text, and skip reasons, are untrusted data. Validate URLs before
navigating and use text APIs rather than HTML interpolation.

## Remediation compatibility alias

`priority_weight` is a severity-derived ordering value, not a predicted score
increase. `impact_pts` has the same integer value and is retained throughout the
`1.2.x` release line as a deprecated compatibility alias. New consumers should
read `priority_weight`; removal of the alias would require a later schema
version. Producers must not write different values for the two names.

## Privacy

JSON output is uncapped even when the HTML renderer shortens very large finding
item lists. Review the complete artifact before sharing it. The authoritative
comparison of local HTML, uncapped JSON, CI logs, GitHub Actions artifacts, and
Claude conversation context is the [report-sharing privacy matrix](../SECURITY.md#report-sharing-privacy-matrix).

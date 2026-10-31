# Rubric format

A "rubric pack" is a directory of YAML files. The grader ships two:
`strict` (stricter thresholds) and `pragmatic` (more permissive
thresholds). Both use provisional maintainer judgment; preview grades are review
aids, not certification. Users can fork either one or write their own and pass it
via `--rubric PATH`.

This document is the contract. The format is the user-facing IP.

Configuration YAML must use UTF-8 encoding. Malformed YAML, YAML aliases (`*name` references to an anchor; a plain anchor with no alias still loads),
nesting deeper than 64 levels, invalid scalar values, numeric `_meta.yaml` fields
outside their ranges, invalid or undeclared rule params (see
[Rule params](RUBRIC_FORMAT.md#rule-params)), and unknown keys (see
[Unknown keys](RUBRIC_FORMAT.md#unknown-keys-and-x_-extensions)) raise
`RubricValidationError` through the loader API. The CLI reports a configuration
error with exit code 3 before publishing HTML or JSON reports.

## Pack layout

```
my_pack/
├── _meta.yaml              # weights, severity, grade scale, version
├── schema_hygiene.yaml     # one file per category
├── naming.yaml
├── segments.yaml
├── calc_metrics.yaml
├── attribution.yaml
└── governance.yaml
```

The grader globs `*.yaml` in the pack directory; files starting with
`_` are reserved for pack metadata. Filenames are otherwise free.

## `_meta.yaml`

```yaml
pack: strict
version: "2.0"
description: |
  Strict rubric encoding the opinions of an Adobe Master / CJA Developer
  about what a high-quality CJA or AA implementation looks like.

# Category weights MUST sum to 1.0 (within float tolerance).
# Categories with weight 0 are excluded from the overall score.
category_weights:
  schema_hygiene:        0.15
  naming_consistency:    0.10
  segment_complexity:    0.15
  calc_metric_maint:     0.20
  attribution_coverage:  0.15
  governance_posture:    0.25

# Severity weights determine how much each fired rule penalizes its
# category subtotal.
severity_weights:
  critical: 4
  high:     3
  medium:   2
  low:      1

# Letter grade thresholds. Score is 0-100. Bands MUST be strictly
# descending and the lowest band MUST start at 0.
grade_scale:
  - { min: 93, grade: "A"  }
  - { min: 90, grade: "A−" }
  - { min: 87, grade: "B+" }
  # …
  - { min: 0,  grade: "F"  }
```

The loader rejects malformed `_meta.yaml` with `RubricValidationError`
and exit code 3.

Numeric fields are deliberately strict:

- category weights are finite numbers from 0 through 1 and must sum to
  1.0;
- severity weights are positive YAML integers (booleans and fractional
  values are not integers); and
- grade-band minima are finite numbers from 0 through 100, in strictly
  descending order, with a final band at 0.

Quoted numeric strings, booleans, negative values, NaN, and infinity
are rejected rather than coerced.

## Category file

Governance boolean parameters (`history_present` / `History Present` and
`sdr_doc_present` / `SDR Doc Present`) accept booleans and trimmed,
case-insensitive `true` / `false` strings. Null falls through to runtime or
metadata evidence; false stops fallback. Aliases within a selected source
must agree. Unsupported values or conflicting aliases produce a rubric error
(CLI exit 3) without publishing a new report. Validation happens when the pack
loads, so it also applies to rules that are suppressed or that do not run for
the snapshot's platform.

Opt-in custom `snapshot_age` (GOV-002) and `doc_drift` (GOV-006) checks use
the shared UTC timestamp parser. ISO numeric offsets and fractional seconds
now carry the same evidence as equivalent `Z` timestamps; naive/date-only
inputs still mean UTC. The shared fixed GMT/UTC/PST/PDT abbreviation allowlist
also applies. Invalid or unavailable dates remain no-ops. Snapshot age still
uses whole elapsed days and a strict `age_days > max_age_days` comparison;
document drift still requires a modification strictly after the update and
a rate strictly above its threshold. References remain explicitly supplied,
with no wall-clock fallback. These checks remain absent from bundled packs.
Expanded date recognition can restore findings, lower scores, and change a
passing threshold exit to 2 in custom packs.

Each non-meta YAML file declares one category and a list of rules.

```yaml
category: schema_hygiene
description: Schema hygiene rules — completeness and quality of components.

rules:
  - id: SCH-003
    name: Components lacking descriptions
    severity: medium                # critical | high | medium | low
    platforms: [cja, aa]            # which platforms this rule applies to
    check: missing_descriptions     # name of registered check function
    params:
      threshold: 0.56               # maintainer-selected; see the private
                                    # evidence boundary in CALIBRATION_CORPUS.md
      targets: [metrics, dimensions]
    rationale: |
      Descriptions are the primary way new analysts and AI agents understand
      what a component measures.
    remediation: |
      Generate the list of components missing descriptions via the data view
      API and populate them.
```

### Validation rules

When the grader loads a pack, it validates:

- Every rule has a registered `check` function (Python).
- `severity` is one of the four known values.
- `platforms` is a non-empty list containing only `aa` and/or `cja`.
- `params` is a mapping (or omitted).
- Rule IDs are unique within the pack and are printable text of at most
  64 characters.
- Each category referenced by a rule appears in `_meta.yaml.category_weights`.
- Two files can share the same `category:` slug — their rules merge.
- Malformed YAML is reported with the affected filename and no parser
  traceback.

Any failure raises `RubricValidationError` and exits 3. Failures are
loud by design: a malformed rubric should never silently degrade.

## Rule params

Each check declares the `params` it reads, and the rubric loader validates
them before grading. A key the rule's check does not declare is a
configuration error, so a misspelled param can never silently fall back to
a default or disable the check. Bounds are inclusive. Number params accept
integers; integer params reject floats such as `5.0` and booleans. "Or null"
means an explicit `null` behaves as if the key were absent; every other
param rejects `null`.

Collection names are `calculated_metrics`, `derived_fields`, `dimensions`,
`metrics` and `segments`. Timestamps may be quoted strings or unquoted YAML
dates. The `sdr_doc_present` and `history_present` overrides also accept
their spaced aliases; aliases that disagree are an error.

Checks not listed take no params.

<!-- param-contracts:start -->
| Check | Param | Accepted value |
| --- | --- | --- |
| `attribution_missing` | `threshold` | number in [0, 1] |
| `broken_references` | `exclude_unresolved_calculated_metric_segments` | true or false |
| `calc_complexity_threshold` | `max_complexity` | number >= 0 |
| `calc_deprecated_allocations` | `deprecated_allocations` | list of strings |
| `calc_formula_broken_refs` | `exclude_unresolved_calculated_metric_segments` | true or false |
| `calc_metrics_missing_descriptions` | `threshold` | number in [0, 1] |
| `calc_near_duplicates` | `min_similarity` | number in [0, 1] |
| `casing_consistency` | `min_consistency` | number in [0, 1] |
| `casing_consistency` | `tag_filter` | string, or null |
| `casing_consistency` | `target` | one collection name |
| `doc_drift` | `last_sdr_update_at` | date or timestamp, or null or empty |
| `doc_drift` | `threshold` | number in [0, 1] |
| `duplicate_component_names` | `targets` | non-empty list of collection names |
| `launch_required_data_elements` | `required` | list of strings, or null |
| `missing_descriptions` | `targets` | non-empty list of collection names |
| `missing_descriptions` | `threshold` | number in [0, 1] |
| `missing_owners` | `threshold` | number in [0, 1] |
| `missing_tags` | `threshold` | number in [0, 1] |
| `orphan_calc_metrics` | `threshold` | number in [0, 1] |
| `orphan_segments` | `threshold` | number in [0, 1] |
| `persistence_lookback_exceeds_cap` | `cap_days` | integer >= 0 |
| `prefix_consistency` | `min_consistency` | number in [0, 1] |
| `prefix_consistency` | `tag_filter` | string, or null |
| `prefix_consistency` | `target` | one collection name |
| `regex_match_id` | `pattern` | regular expression string |
| `regex_match_id` | `targets` | non-empty list of collection names |
| `sdr_doc_absent` | `SDR Doc Present` | true or false (or "true"/"false"), or null |
| `sdr_doc_absent` | `sdr_doc_present` | true or false (or "true"/"false"), or null |
| `segment_nesting_depth` | `max_depth` | integer >= 0 |
| `segments_missing_descriptions` | `threshold` | number in [0, 1] |
| `semantic_consistency` | `synonym_groups` | list of word groups (2+ words each), or null |
| `snapshot_age` | `max_age_days` | integer >= 0 |
| `snapshot_age` | `reference_date` | date or timestamp, or null or empty |
| `snapshot_history_absent` | `History Present` | true or false (or "true"/"false"), or null |
| `snapshot_history_absent` | `history_present` | true or false (or "true"/"false"), or null |
<!-- param-contracts:end -->

## Unknown keys and `x_` extensions

Every fixed-shape mapping rejects keys it does not recognize. The error
names the file, the rule ID where there is one, and the key, and adds a
"did you mean" hint when a close match exists:

| Where | Accepted keys |
| --- | --- |
| `_meta.yaml` | `pack`, `version`, `description`, `category_weights`, `severity_weights`, `grade_scale` |
| `grade_scale` entry | `min`, `grade` |
| Category file | `category`, `description`, `rules` |
| Rule entry | `id`, `name`, `severity`, `platforms`, `check`, `params`, `rationale`, `remediation` |
| Rule `params` | the keys its check declares (table above) |

To keep your own notes in a pack, prefix the key with `x_` (lowercase), for
example `x_owner: analytics` or `x_ticket: SDR-142`. The grader ignores `x_`
keys at every level above; they never change a grade or a report. Inside
`category_weights` and `severity_weights` an `x_` key is not skipped: it is
read as a category or severity name like any other key.

**Migrating a custom pack:** if a pack that loaded before now fails, the
message names the key. Fix the spelling, delete the key, or rename it with
an `x_` prefix.

## Multiple platforms

The `platforms` field lists which platforms a rule applies to. Most
rules are `[cja, aa]`. A rule that only makes sense for one platform
opts into a single platform via `platforms: [aa]` or `[cja]`; the
engine skips it when the snapshot's platform doesn't match.

## Rule IDs

Convention: `<CATEGORY-PREFIX>-<NUMBER>`. The default packs use
`SCH`, `NAME`, `SEG`, `CALC`, `ATTR`, and `GOV`. Forked packs are free
to introduce new prefixes; just keep IDs stable so the JSON output
remains comparable across runs and packs.

## Forking guidance

Copying a bundled pack is a **source-checkout workflow**; `src/` is not a
portable installed-command path and the CLI has no pack-export command. From
the repository root of a checkout at the release you want to fork:

1. Copy `src/sdr_grader/rules/packs/strict/` to your own directory.
2. Edit thresholds in each rule's `params:` block.
3. Run `sdr-grader path/to/snapshot.json --rubric path/to/your_pack`.

The copied `my_pack/` directory is portable after step 1. If you have only an
installed wheel, create the directory and YAML files from the contract above.

## Effective-rule safety

Pack validation proves that YAML is structurally valid; it does not prove that
any rule applies to a particular platform. Platform filtering and full-rule
suppression can leave an empty effective rule inventory. The current scoring
contract gives categories with no effective rules 100%, so that configuration
can yield a technically valid but meaningless A / 100 report. Before using a
custom pack as a gate, verify that it contains at least one unsuppressed rule
for every platform you grade.

To extend with a new check function, see [CHECK_FUNCTION_GUIDE.md](CHECK_FUNCTION_GUIDE.md).

## Reference grading policy parameter

For `broken_references` and `calc_formula_broken_refs`, policy 2.1 sets:

```yaml
params:
  exclude_unresolved_calculated_metric_segments: true
```

The value must be a YAML boolean. Omitted or `false` preserves prior scoring,
including in custom packs. This is check-name based and works with custom rule
IDs. The flag excludes only unresolved, unambiguously typed calculated-metric
segment references; other checks and mixed penalties stay active. Excluded-only
rules leave the severity denominator and are disclosed as not assessed.

This parameter was introduced in pack 2.1 with grader 1.4.0 and remains enabled
in default packs 3.0. Older graders ignore this parameter. Pack 3.0 additionally
requires the new AA administration check implementations and therefore grader
1.5.0 or later. The v1.5.0 tag first includes both pack 3.0 and those checks;
1.4.0 cannot load pack 3.0. This guide targets grader 1.6.2. See
[AA administration evidence](AA_ADMIN_INPUT.md).
Version text
alone does not enable policy behavior. See
[Reference grading policy](REFERENCE_GRADING_POLICY.md).

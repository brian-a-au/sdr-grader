# Rubric format

A "rubric pack" is a directory of YAML files. The grader ships two:
`strict` (master-cert-grade opinion) and `pragmatic` (sanity-check
thresholds). Users can fork either one or write their own and pass it
via `--rubric PATH`.

This document is the contract. The format is the user-facing IP.

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
version: "0.4"
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

## Category file

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
      threshold: 0.10
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
- `params` is a mapping (or omitted).
- Rule IDs are unique within the pack.
- Each category referenced by a rule appears in `_meta.yaml.category_weights`.
- Two files can share the same `category:` slug — their rules merge.

Any failure raises `RubricValidationError` and exits 3. Failures are
loud by design: a malformed rubric should never silently degrade.

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

To fork:

1. Copy `src/sdr_grader/rules/packs/strict/` to your own directory.
2. Edit thresholds in each rule's `params:` block.
3. Run `sdr-grader path/to/snapshot.json --rubric path/to/your_pack`.

To extend with a new check function, see [CHECK_FUNCTION_GUIDE.md](CHECK_FUNCTION_GUIDE.md).

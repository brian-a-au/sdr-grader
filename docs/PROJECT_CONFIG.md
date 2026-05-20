# Project config (`.sdr-grader.yaml`)

A `.sdr-grader.yaml` file in your working directory tunes the grader to
your project's context — silencing rules that don't apply, reweighting
categories that matter more to you, or downgrading the severity of a
rule you accept but want recorded. The file is opt-in. Without one, the
selected rubric pack runs unmodified.

## Discovery

By default the grader looks for `./.sdr-grader.yaml` in the working
directory at startup. Pass `--suppress-config PATH` to point at a
different file (the flag errors if `PATH` doesn't exist; the default
filename is silently absent).

## Schema

```yaml
suppress:
  - rule: NAME-002
    reason: "We use legacy IDs with hyphens; agreed by team."
  - rule: SCH-004
    reason: "Tracked in JIRA SDR-142; ignoring until cleanup ships."

severity_overrides:
  CALC-014: medium      # demoted from high
  GOV-001: low          # we treat this as an FYI

category_weights:
  governance_posture: 0.30
  schema_hygiene:     0.20
```

All three top-level keys are optional; omit any you don't need.

### `suppress`

A list of suppression entries. Each entry must have:

- `rule` *(required, string)* — the rule ID to suppress, e.g. `NAME-002`.
- `reason` *(optional, string)* — free-text explanation. Surfaces in the
  rendered report's methodology section under the rule ID, so reviewers
  can see *why* a rule was silenced rather than wondering whether it
  was missed.
- `components` *(optional, list of strings)* — currently declared but
  not actively applied: the v0.1 finding shape doesn't carry per-component
  identity, so component-level suppressions are passed through and noted
  in the methodology summary. Whole-rule suppression is the only
  enforcement today. Tracked for a future release.

### `severity_overrides`

A mapping of rule ID → new severity. The value must be one of
`critical`, `high`, `medium`, `low`. Overrides affect the scoring math
(severity weights come from the pack's `_meta.yaml`) and the rendered
report's severity badge, but don't change whether the rule fires.

### `category_weights`

A mapping of category slug → numeric weight. Overrides are merged into
the pack's `category_weights` map, then the full set is re-normalized to
sum to 1.0. You can rebalance one or two categories without restating
all six — unspecified categories keep their original ratios.

Categories with weight 0 are excluded from the overall score entirely,
which is useful when a whole category doesn't apply to your project.

## Validation

Any structural problem in the file (non-mapping at the root, malformed
suppress entry, invalid severity value, non-numeric weight) raises
`RubricValidationError` and exits with code 3. Failures are loud by
design: a typo'd suppression should never silently let a rule keep firing
when you thought you'd silenced it.

## How suppressions show up in the report

The rendered HTML's methodology section lists suppressed rule IDs
grouped by reason, so anyone reviewing the report can see at a glance
which rules were silenced and why. Severity overrides apply transparently
— a `CALC-014` finding rendered after a `medium` override looks like
any other medium-severity finding.

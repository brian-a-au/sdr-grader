# Customizing the grader

`sdr-grader` is rule-based, and almost every layer is something you can
tune for your project — from silencing a single noisy rule up through
adding a whole new platform. This doc maps each customization need to
the right mechanism so you don't reach for the heaviest tool first.

## Pick a mechanism

| You want to…                                          | Use…                                       | Lift             |
|-------------------------------------------------------|--------------------------------------------|------------------|
| Silence a rule you accept (with a reason on the report) | `.sdr-grader.yaml` `suppress:`             | One YAML entry   |
| Demote a rule's severity for your context              | `.sdr-grader.yaml` `severity_overrides:`   | One YAML entry   |
| Rebalance category weights                             | `.sdr-grader.yaml` `category_weights:`     | One YAML entry   |
| Change a rule's threshold (e.g. `max_segments`)        | Fork the rubric pack, edit `params:`       | New pack dir     |
| Add a brand-new rule                                   | New check function + YAML entry            | Python + YAML    |
| Grade against data the snapshot doesn't carry          | `--extra-input KEY=PATH` + opt-in rule     | One CLI flag     |
| Support a new platform                                 | New adapter                                | New module       |

The right answer is the first row you can live with. Suppression keeps
you on the bundled packs, so rubric upgrades stay easy. Forking locks
you to a snapshot of the rubric and you own the merge cost forever.

## Tuning an existing pack

These are the "don't fork" knobs. Drop a `.sdr-grader.yaml` in your
working directory and the grader auto-discovers it. Suppressed rules
and severity overrides surface in the rendered report's methodology
section, so reviewers can see what was muted and why.

```yaml
suppress:
  - rule: NAME-002
    reason: "We use legacy IDs with hyphens; agreed by team."

severity_overrides:
  CALC-014: medium

category_weights:
  governance_posture: 0.30
```

See [PROJECT_CONFIG.md](PROJECT_CONFIG.md) for the full schema and
validation rules.

### What `.sdr-grader.yaml` does not do today

It does not override a rule's `params:` (thresholds, allowed lists).
Changing `max_segments` from 200 to 350, or relaxing `min_consistency`
from 0.80 to 0.65, currently requires forking the pack. Tracked for
a future release; in the meantime, fork the pack and pin the version.

## Forking a rubric pack

Fork when you need to change a threshold inside a rule's `params:`,
add a rule the default packs don't ship, or remove a rule entirely
rather than suppress it.

```bash
cp -R src/sdr_grader/rules/packs/strict my_pack/
# edit thresholds inside the per-category YAMLs
sdr-grader snapshot.json --rubric my_pack/
```

Bump `version:` in your fork's `_meta.yaml` whenever the thresholds
change. Trend reports and distribution leaderboards across mixed pack
versions are visually clean but semantically misleading — scores
aren't comparable once the underlying rubric drifts between runs.

See [RUBRIC_FORMAT.md](RUBRIC_FORMAT.md) for the pack layout and
loader validation.

## Adding a new rule

Adding a *rule* is a YAML entry. Adding a new *kind* of check is a
Python function plus a YAML reference. Most "new rule" requests turn
out to be the former — the bundled check functions are parameterized,
so you can often add a YAML entry with different `params:` and get a
new rule for free.

If you do need a new check function, the contract is short: pure
function, deterministic, returns `list[Finding]`. See
[CHECK_FUNCTION_GUIDE.md](CHECK_FUNCTION_GUIDE.md).

## Grading against external data

Some rules need data the snapshot itself doesn't carry — Launch
property exports, eVar cardinality, an SDR doc's last-updated
timestamp. The CLI attaches arbitrary JSON via
`--extra-input KEY=PATH`; rules opt in by reading
`impl.supplementary_data[KEY]` and stay silent when the key is
absent.

This is also the answer when "I want to grade against my Workspace
project usage" or similar — there is no built-in importer, but
anything you can shape into JSON is fair game.

See [SUPPLEMENTARY_INPUTS.md](SUPPLEMENTARY_INPUTS.md).

## Adding a new platform

The adapter layer is the boundary between platform-specific
vocabulary and the normalized model the rules see. Adding a third
platform means producing the same `Implementation` shape from
whatever JSON your platform emits — roughly the same ~300 LoC of
mapping code the CJA and AA reference adapters carry.

See [ADAPTER_GUIDE.md](ADAPTER_GUIDE.md).

## Keeping customizations sustainable

A few habits that make customization less painful six months in:

- **Always record a reason on suppressions.** It surfaces in the
  rendered report's methodology section, so reviewers don't have to
  wonder whether a rule was missed or muted.
- **Version your fork.** Bump `_meta.yaml`'s `version:` on every
  threshold change so trend reports and distribution data stay
  comparable.
- **Prefer suppression over forking** when a rule is genuinely noisy
  in your context. The bundled packs evolve; `.sdr-grader.yaml`
  travels with you across pack upgrades. Forks freeze.
- **Don't suppress to hit a grade.** The methodology section reveals
  what was muted; a suppressed-to-pass report is more embarrassing
  than a low one.

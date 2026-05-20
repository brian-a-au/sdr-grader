# Supplementary inputs (`--extra-input`)

Some rules grade against data that the snapshot itself doesn't carry —
external evidence the operator has but the auto-SDR exporters don't
collect. The `--extra-input` mechanism lets you attach that JSON at
run time without modifying the snapshot or forking the adapter.

## Usage

```bash
sdr-grader snapshot.json --extra-input KEY=path/to/data.json
```

The flag is repeatable; pass it once per attached file:

```bash
sdr-grader snapshot.json \
  --extra-input launch=launch_property.json \
  --extra-input cardinality=evar_cardinality.json
```

The CLI loads each file and stores its parsed JSON under
`Implementation.supplementary_data[KEY]`. The key name is whatever the
rule's check function asks for — there's no global registry — and the
shape of the JSON is the *rule's* contract.

## There are no built-in exporters

Nothing in `sdr-grader` produces these files for you. The operator
supplies whatever JSON the rule's docstring asks for, sourcing it from
whatever tool naturally exports that data (a Launch API export, an AEP
profile-store query, a custom SDR pipeline, a hand-edited file).

This is intentional. The grader stays a pure linter; the data-fetch
problem belongs upstream.

## Opt-in by absence

A supplementary-input rule reads the key it needs and stays silent if
the key is missing:

```python
launch = impl.supplementary_data.get("launch")
if not isinstance(launch, dict):
    return []
```

So an opt-in rule simply doesn't fire on snapshots that don't attach
its key. There's no error, no warning, no penalty in the score — it's
as if the rule wasn't in the pack for that run. This lets the same
rubric pack run across snapshots with and without supplementary data
without changes.

## Worked example: `LAUNCH-001`

`src/sdr_grader/rules/checks/supplementary.py` contains the worked
example. Its docstring documents the expected JSON shape — start there
when writing your own supplementary-input check:

```json
{
  "property": {"name": "Production Web"},
  "data_elements": [
    {"name": "page_name", "type": "..."},
    {"name": "user_id",   "type": "..."}
  ]
}
```

The check fires when required data elements (declared in the rule's
`params.required` list) are missing from the attached `data_elements`
array.

## Writing a new supplementary check

See [docs/CHECK_FUNCTION_GUIDE.md](CHECK_FUNCTION_GUIDE.md) for the
check function contract. The supplementary-input pattern is just a
normal check function that happens to read `impl.supplementary_data`
instead of (or in addition to) the normalized component data.

# Writing a platform adapter

Adapters know vocabularies; rules don't. Adding a new platform is a
matter of producing the normalized `Implementation` model from whatever
JSON shape the platform's snapshot tool emits.

## Where to start

The two reference adapters live at:

- `src/sdr_grader/adapters/cja.py` — reads `cja_auto_sdr` JSON output.
- `src/sdr_grader/adapters/aa.py` — reads `aa_auto_sdr` JSON output.

Read both. They are small (~300 LoC each) and demonstrate the pattern.

## The contract

```python
def adapt(snapshot: dict[str, Any], *, source: str = "<unknown>") -> Implementation:
    """Convert a parsed JSON snapshot into a normalized Implementation."""
```

The function takes a parsed dict (the loader handles file IO and JSON
parsing) and returns an `Implementation` (see `src/sdr_grader/core/models.py`). No async, no
I/O, no globals.

## Responsibilities

The adapter must:

1. **Validate the input shape.** Raise `InvalidSnapshotError` with an
   explicit message when required fields are missing or malformed. The
   grader exits 1 on these, so "shape doesn't match this platform" is a
   useful signal — operators can re-run with `--platform` overridden.
2. **Map platform vocabulary** to the normalized model:
   - eVars + props (AA) -> `dimensions`
   - events (AA) / metrics (CJA) -> `metrics`
   - segments -> `segments`
   - calculated metrics -> `calculated_metrics`
   - derived fields (CJA-only) -> `derived_fields`
3. **Compute derived fields.** Segment nesting depth, distinct
   container contexts, calc metric reference lists, complexity scores.
   Some of these come from the upstream snapshot directly; others
   require parsing JSON-encoded `definition_json` strings.
4. **Preserve raw JSON.** Set `Implementation.raw = snapshot` so rules
   that need platform-specific access can drill in. Most rules
   shouldn't need this — surface what you can in `platform_specific`
   on each component.
5. **Normalize sentinels.** cja_auto_sdr writes `"-"` for missing
   descriptions; AA may use `null`. The adapter must coerce both to
   `None` so rules don't have to learn each platform's convention.
6. **Self-report version.** Read the upstream tool's version from the
   snapshot metadata and put it in `Implementation.adapter_version`.
   This goes into the rendered report's "Adapter" field.

## Auto-detection

Add a discriminator branch to `src/sdr_grader/input/detect.py`. The
function inspects top-level keys and returns a platform string:

- CJA: `metadata` object with a `Data View ID` key.
- AA: `report_suite` object with an `rsid` key.

If your shape is similar to one of these, prefer a more specific marker
(a unique top-level key) so detection stays unambiguous.

## CLI dispatch

Add a branch to `src/sdr_grader/cli/main.py::_adapt_snapshot()`:

```python
if platform == "your_platform":
    from sdr_grader.adapters.your_platform import adapt
    return adapt(snapshot, source=source)
```

## Supplementary inputs

Some rules need data the snapshot itself doesn't carry. Rather than
building a dedicated adapter for each side input, the CLI accepts
arbitrary JSON files attached at run time:

```bash
sdr-grader snapshot.json --extra-input KEY=PATH
```

The CLI parses each spec, loads the JSON, and stores it under
`Implementation.supplementary_data[KEY]`. The key name and the JSON
shape are entirely the rule's contract — there is no schema, no
adapter, and no built-in exporter that produces these files. Operators
supply whatever JSON the rule's docstring asks for.

Rules opt in by reading the key they need and returning empty when it's
absent, so an opt-in rule stays silent on snapshots that don't attach
it:

```python
@register_check("my_supplementary_check")
def check_my_supplementary_check(impl, ctx) -> list[Finding]:
    data = impl.supplementary_data.get("my_key")
    if not isinstance(data, dict):
        return []  # rule is opt-in; key not attached -> no findings
    # … inspect `data` and emit findings …
```

For a worked example, see `LAUNCH-001`
(`launch_required_data_elements` in
`src/sdr_grader/rules/checks/supplementary.py`). Its docstring
documents the JSON shape it expects and is the template to follow when
adding new supplementary-input rules.

## Vendoring parity with sdr-visualizer

`adapters/{cja,aa}.py` share a defensive-coercion layer with
[`sdr-visualizer`](https://github.com/brian-a-au/sdr-visualizer) per
SPEC §11/§15. The adapters are not byte-identical, but changes to these
shared helpers must be mirrored to the sibling repository in the same cycle:

- `_parse_tag_list` / `_parse_ref_list` parse JSON-encoded list strings,
  tolerate native lists, and drop unparseable values to `[]`.
- `_optional_list` (AA) treats an absent optional section as `[]` while a
  present non-list raises `InvalidSnapshotError`; CJA gets the equivalent
  guarantee through `_section_records`.
- `TESTED_THROUGH_GENERATOR_VERSION`, `generator_version_warning`, and
  `_version_tuple` implement the Q5 compatibility warning. Helper behavior is
  identical; the constant value is deliberately platform- and release-specific.
- `_optional_timestamp` keeps `created_at` / `modified_at` only when already a
  non-empty string, so malformed timestamp scalars become missing values.
- `_optional_str` (CJA) guards derived-field `data_type` with the same
  `str(x) if x else None` coercion used by the visualizer. Grader-side `owner`
  safety comes through `_normalize_owner`: a different mechanism with the same
  defensive outcome, so no owner-specific `_optional_str` mirror is needed.

## Testing

Mirror `tests/test_adapters_cja.py` / `tests/test_adapters_aa.py`. Cover
at least:

- Round-trip of every record kind.
- Sentinel normalization (e.g. `"-"` -> `None`).
- Derived-field computation (segment depth, calc complexity, references).
- Validation failures (missing top-level keys, wrong types).

Use a small, deterministic builder script under `scripts/` and check
both the messy and clean fixtures into `tests/fixtures/` so downstream
rule tests can assert specific counts against them.

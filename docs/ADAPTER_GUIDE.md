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
parsing) and returns an `Implementation` (see SPEC §5). No async, no
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

## Supplementary inputs (Launch / Workspace / AEP exports)

Some rule packs need data the snapshot doesn't carry — Launch property
exports, Workspace project exports, AEP governance API outputs, etc.
Rather than building a dedicated adapter for each, attach those files
through the `--extra-input KEY=PATH` flag. The CLI parses each spec,
loads the JSON, and stores it in `Implementation.supplementary_data[KEY]`.

```bash
sdr-grader snapshot.json \
  --extra-input launch=launch_property.json \
  --extra-input workspace=workspace_export.json
```

Rules opt in by reading `impl.supplementary_data.get("launch")` and
returning empty when the key is absent, so a rule that needs Launch
data quietly does nothing on snapshots that don't supply it.

```python
@register_check("launch_required_data_elements")
def check_launch_required_data_elements(impl, ctx) -> list[Finding]:
    launch = impl.supplementary_data.get("launch")
    if not isinstance(launch, dict):
        return []  # rule is opt-in via --extra-input launch=…
    # … walk the Launch export and emit findings …
```

The shape of each supplementary input is determined by the upstream
exporter; document it next to the rule that consumes it.

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
